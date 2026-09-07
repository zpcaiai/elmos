package io.elmos.productionruntime;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.productionruntime.ProductionRuntimeModels.FinalUsage;
import io.elmos.productionruntime.ProductionRuntimeModels.IdempotencyState;
import io.elmos.productionruntime.ProductionRuntimeModels.MeterSnapshot;
import io.elmos.productionruntime.ProductionRuntimeModels.ModelCallReceipt;
import io.elmos.productionruntime.ProductionRuntimeModels.ModelCallStatus;
import io.elmos.productionruntime.ProductionRuntimeModels.ReservationResult;
import io.elmos.productionruntime.ProductionRuntimeModels.ReservationStatus;
import io.elmos.productionruntime.ProductionRuntimeModels.ReserveRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.TopUpRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.TopUpResult;
import io.elmos.productionruntime.ProductionRuntimeModels.TopUpStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.support.TransactionTemplate;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.sql.ResultSet;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

/**
 * PostgreSQL billing adapter for prepaid execution.
 *
 * <p>Each public operation binds tenant context and runs under one local
 * transaction. The service deliberately has no API for changing balances
 * outside reserve, release, settle, or verified top-up.</p>
 */
public final class JdbcProductionBillingService implements ProductionBillingPort {
    private static final String RESERVE_OPERATION = "CREDIT_RESERVE";
    private static final String SETTLE_OPERATION = "CREDIT_SETTLE";
    private static final String TOP_UP_OPERATION = "TOP_UP";

    private final JdbcClient jdbc;
    private final TransactionTemplate transactions;
    private final ObjectMapper json;

    public JdbcProductionBillingService(JdbcClient jdbc, TransactionTemplate transactions, ObjectMapper json) {
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
        this.transactions = Objects.requireNonNull(transactions, "transactions");
        this.json = Objects.requireNonNull(json, "json");
    }

    @Override
    public ReservationResult reserve(ReserveRequest request) {
        return inTenant(request.tenantId(), () -> {
            String requestHash = hash(request.tenantId() + "|" + request.walletId() + "|" + request.workItemId() + "|" + request.amount() + "|" + request.expiresAt());
            var existing = findIdempotency(request.tenantId(), RESERVE_OPERATION, request.idempotencyKey());
            if (existing != null) {
                assertRequestHash(existing.requestHash(), requestHash);
                if (existing.state() == IdempotencyState.SUCCEEDED) {
                    return reservationById(existing.resourceId());
                }
                throw new ProductionRuntimeException("BILLING_RESERVATION_IN_PROGRESS", "reservation must be reconciled before retry");
            }
            insertIdempotency(request.tenantId(), RESERVE_OPERATION, request.idempotencyKey(), requestHash);
            var balance = jdbc.sql("""
                    select wb.available_balance, wb.reserved_balance
                      from billing.wallet_balances wb
                      join billing.wallets w on w.id = wb.wallet_id
                     where wb.wallet_id = :walletId and w.tenant_id = :tenantId
                     for update
                    """).param("walletId", request.walletId()).param("tenantId", request.tenantId())
                    .query((rs, row) -> new Balance(rs.getBigDecimal("available_balance"), rs.getBigDecimal("reserved_balance"))).optional()
                    .orElseThrow(() -> new ProductionRuntimeException("BILLING_WALLET_NOT_FOUND", "wallet is not bound to tenant"));
            assertReservationAdmission(request.tenantId(), request.amount());
            if (balance.available().compareTo(request.amount()) < 0) {
                failIdempotency(request.tenantId(), RESERVE_OPERATION, request.idempotencyKey(), "CREDIT_EXHAUSTED");
                throw new ProductionRuntimeException("CREDIT_EXHAUSTED", "available credit is insufficient");
            }
            UUID reservationId = UUID.randomUUID();
            jdbc.sql("""
                    insert into billing.credit_reservations
                        (id, tenant_id, wallet_id, project_id, job_id, work_item_id,
                         reservation_idempotency_key, reserved_amount, expires_at)
                    values (:id, :tenantId, :walletId, :projectId, :jobId, :workItemId,
                            :key, :amount, :expiresAt)
                    """).param("id", reservationId).param("tenantId", request.tenantId())
                    .param("walletId", request.walletId()).param("projectId", request.projectId())
                    .param("jobId", request.jobId()).param("workItemId", request.workItemId())
                    .param("key", request.idempotencyKey()).param("amount", request.amount())
                    .param("expiresAt", OffsetDateTime.ofInstant(request.expiresAt(), ZoneOffset.UTC))
                    .update();
            jdbc.sql("""
                    update billing.wallet_balances
                       set available_balance = available_balance - :amount,
                           reserved_balance = reserved_balance + :amount,
                           version = version + 1,
                           updated_at = now()
                     where wallet_id = :walletId
                    """).param("amount", request.amount()).param("walletId", request.walletId()).update();
            var response = reservationById(reservationId);
            completeIdempotency(request.tenantId(), RESERVE_OPERATION, request.idempotencyKey(), reservationId, response);
            return response;
        });
    }

    @Override
    public void release(UUID tenantId, UUID reservationId, String reason) {
        inTenant(tenantId, () -> {
            var reservation = jdbc.sql("""
                    select id, wallet_id, reserved_amount, consumed_amount, status
                      from billing.credit_reservations
                     where tenant_id = :tenantId and id = :id
                     for update
                    """).param("tenantId", tenantId).param("id", reservationId)
                    .query((rs, row) -> new ReservationRow(
                            rs.getObject("id", UUID.class), rs.getObject("wallet_id", UUID.class),
                            rs.getBigDecimal("reserved_amount"), rs.getBigDecimal("consumed_amount"),
                            ReservationStatus.valueOf(rs.getString("status"))))
                    .optional().orElseThrow(() -> new ProductionRuntimeException("BILLING_RESERVATION_NOT_FOUND", "reservation not found"));
            if (reservation.status() != ReservationStatus.ACTIVE) return null;
            BigDecimal unused = reservation.reservedAmount().subtract(reservation.consumedAmount());
            jdbc.sql("""
                    update billing.wallet_balances
                       set available_balance = available_balance + :amount,
                           reserved_balance = reserved_balance - :amount,
                           version = version + 1,
                           updated_at = now()
                     where wallet_id = :walletId
                    """).param("amount", unused).param("walletId", reservation.walletId()).update();
            jdbc.sql("""
                    update billing.credit_reservations
                       set status = 'RELEASED', settled_at = now(), last_transition_reason = :reason
                     where id = :id and status = 'ACTIVE'
                    """).param("reason", boundedReason(reason)).param("id", reservationId).update();
            outbox(tenantId, "CREDIT_RESERVATION", reservationId, "CREDIT_RELEASED", Map.of("amount", unused, "reason", boundedReason(reason)));
            return null;
        });
    }

    @Override
    public void settle(FinalUsage usage) {
        inTenant(usage.tenantId(), () -> {
            String key = "settle:" + usage.reservationId();
            String requestHash = hash(usage.toString());
            var existing = findIdempotency(usage.tenantId(), SETTLE_OPERATION, key);
            if (existing != null) {
                assertRequestHash(existing.requestHash(), requestHash);
                if (existing.state() == IdempotencyState.SUCCEEDED) return null;
                throw new ProductionRuntimeException("BILLING_SETTLEMENT_IN_PROGRESS", "settlement must be reconciled before retry");
            }
            insertIdempotency(usage.tenantId(), SETTLE_OPERATION, key, requestHash);
            var reservation = jdbc.sql("""
                    select id, wallet_id, reserved_amount, consumed_amount, status
                      from billing.credit_reservations
                     where tenant_id = :tenantId and id = :id
                     for update
                    """).param("tenantId", usage.tenantId()).param("id", usage.reservationId())
                    .query((rs, row) -> new ReservationRow(rs.getObject("id", UUID.class), rs.getObject("wallet_id", UUID.class), rs.getBigDecimal("reserved_amount"), rs.getBigDecimal("consumed_amount"), ReservationStatus.valueOf(rs.getString("status"))))
                    .optional().orElseThrow(() -> new ProductionRuntimeException("BILLING_RESERVATION_NOT_FOUND", "reservation not found"));
            if (reservation.status() == ReservationStatus.SETTLED) return null;
            if (reservation.status() != ReservationStatus.ACTIVE) throw new ProductionRuntimeException("BILLING_RESERVATION_NOT_ACTIVE", "only active reservations can settle");
            validateFinalUsage(usage, reservation.reservedAmount());
            assertFinalUsageAdmission(usage);
            validateUsageBindingsAndPricing(usage);
            if (usage.providerUsageId() != null) {
                var duplicate = jdbc.sql("select model_call_id, customer_credit_cost from billing.token_usage_events where provider = :provider and provider_usage_id = :usageId")
                        .param("provider", usage.provider()).param("usageId", usage.providerUsageId()).query((rs, row) -> new ExistingUsage(rs.getObject("model_call_id", UUID.class), rs.getBigDecimal("customer_credit_cost"))).optional();
                if (duplicate.isPresent() && !duplicate.get().modelCallId().equals(usage.modelCallId())) throw new ProductionRuntimeException("BILLING_PROVIDER_USAGE_CONFLICT", "provider usage identity belongs to another model call");
            }
            BigDecimal amount = usage.customerCreditCost();
            BigDecimal unused = reservation.reservedAmount().subtract(amount);
            jdbc.sql("""
                    update billing.wallet_balances
                       set reserved_balance = reserved_balance - :reserved,
                           available_balance = available_balance + :unused,
                           version = version + 1,
                           updated_at = now()
                     where wallet_id = :walletId
                    """).param("reserved", reservation.reservedAmount()).param("unused", unused).param("walletId", reservation.walletId()).update();
            jdbc.sql("""
                    insert into billing.token_usage_events
                      (id, tenant_id, model_call_id, reservation_id, provider, model, provider_usage_id,
                       provider_pricing_version_id, commercial_pricing_version_id, input_tokens,
                       cached_input_tokens, output_tokens, reasoning_tokens, provider_total_cost, customer_credit_cost)
                    values (:id, :tenantId, :modelCallId, :reservationId, :provider, :model, :providerUsageId,
                            :providerPricing, :commercialPricing, :inputTokens, :cachedInputTokens, :outputTokens,
                            :reasoningTokens, :providerCost, :creditCost)
                    """).param("id", UUID.randomUUID()).param("tenantId", usage.tenantId()).param("modelCallId", usage.modelCallId())
                    .param("reservationId", usage.reservationId()).param("provider", usage.provider()).param("model", usage.model())
                    .param("providerUsageId", usage.providerUsageId()).param("providerPricing", usage.providerPricingVersionId())
                    .param("commercialPricing", usage.commercialPricingVersionId()).param("inputTokens", usage.inputTokens())
                    .param("cachedInputTokens", usage.cachedInputTokens()).param("outputTokens", usage.outputTokens())
                    .param("reasoningTokens", usage.reasoningTokens()).param("providerCost", usage.providerTotalCost())
                    .param("creditCost", amount).update();
            jdbc.sql("update billing.credit_reservations set consumed_amount = :amount, status = 'SETTLED', settled_at = now() where id = :id")
                    .param("amount", amount).param("id", usage.reservationId()).update();
            jdbc.sql("update ai_usage.model_calls set status = 'COMPLETE', completed_at = now() where id = :id and tenant_id = :tenantId")
                    .param("id", usage.modelCallId()).param("tenantId", usage.tenantId()).update();
            jdbc.sql("update ai_usage.model_call_receipts set receipt_state = 'COMPLETE', updated_at = now() where tenant_id = :tenantId and model_call_id = :id")
                    .param("tenantId", usage.tenantId()).param("id", usage.modelCallId()).update();
            ledgerAndJournal(usage.tenantId(), reservation.walletId(), "USAGE", usage.reservationId(), amount, "settle:" + usage.reservationId());
            completeIdempotency(usage.tenantId(), SETTLE_OPERATION, key, usage.reservationId(), Map.of("settledAmount", amount));
            outbox(usage.tenantId(), "MODEL_CALL", usage.modelCallId(), "USAGE_SETTLED", Map.of("reservationId", usage.reservationId(), "amount", amount));
            return null;
        });
    }

    @Override
    public MeterSnapshot recordMeter(MeterSnapshot meter) {
        return inTenant(meter.tenantId(), () -> {
            var existing = jdbc.sql("""
                    select sequence_no, cumulative_input_tokens, cumulative_cached_input_tokens,
                           cumulative_output_tokens, cumulative_reasoning_tokens,
                           metered_provider_cost, metered_credit_cost
                      from billing.usage_meter_events
                     where tenant_id = :tenantId and model_call_id = :modelCallId and sequence_no = :sequenceNo
                    """).param("tenantId", meter.tenantId()).param("modelCallId", meter.modelCallId()).param("sequenceNo", meter.sequenceNo())
                    .query((rs, row) -> new MeterSnapshot(meter.tenantId(), meter.reservationId(), meter.modelCallId(), rs.getLong("sequence_no"), rs.getLong("cumulative_input_tokens"), rs.getLong("cumulative_cached_input_tokens"), rs.getLong("cumulative_output_tokens"), rs.getLong("cumulative_reasoning_tokens"), rs.getBigDecimal("metered_provider_cost"), rs.getBigDecimal("metered_credit_cost"))).optional();
            if (existing.isPresent()) {
                if (!sameMeter(existing.get(), meter)) throw new ProductionRuntimeException("USAGE_METER_CONFLICT", "meter sequence was replayed with different values");
                return existing.get();
            }
            var latest = jdbc.sql("select sequence_no, cumulative_input_tokens, cumulative_cached_input_tokens, cumulative_output_tokens, cumulative_reasoning_tokens, metered_provider_cost, metered_credit_cost from billing.usage_meter_events where tenant_id = :tenantId and model_call_id = :modelCallId order by sequence_no desc limit 1 for update")
                    .param("tenantId", meter.tenantId()).param("modelCallId", meter.modelCallId()).query((rs, row) -> new MeterValues(rs.getLong("sequence_no"), rs.getLong("cumulative_input_tokens"), rs.getLong("cumulative_cached_input_tokens"), rs.getLong("cumulative_output_tokens"), rs.getLong("cumulative_reasoning_tokens"), rs.getBigDecimal("metered_provider_cost"), rs.getBigDecimal("metered_credit_cost"))).optional();
            latest.ifPresent(value -> {
                if (meter.sequenceNo() <= value.sequenceNo() || meter.cumulativeInputTokens() < value.inputTokens() || meter.cumulativeCachedInputTokens() < value.cachedTokens() || meter.cumulativeOutputTokens() < value.outputTokens() || meter.cumulativeReasoningTokens() < value.reasoningTokens() || meter.meteredProviderCost().compareTo(value.providerCost()) < 0 || meter.meteredCreditCost().compareTo(value.creditCost()) < 0) throw new ProductionRuntimeException("USAGE_METER_NOT_MONOTONIC", "meter snapshots must be cumulative and monotonic");
            });
            assertMeterAdmission(meter);
            jdbc.sql("""
                    insert into billing.usage_meter_events
                      (tenant_id, reservation_id, model_call_id, sequence_no,
                       cumulative_input_tokens, cumulative_cached_input_tokens,
                       cumulative_output_tokens, cumulative_reasoning_tokens,
                       metered_provider_cost, metered_credit_cost)
                    values (:tenantId, :reservationId, :modelCallId, :sequenceNo,
                            :inputTokens, :cachedTokens, :outputTokens, :reasoningTokens,
                            :providerCost, :creditCost)
                    """).param("tenantId", meter.tenantId()).param("reservationId", meter.reservationId()).param("modelCallId", meter.modelCallId()).param("sequenceNo", meter.sequenceNo()).param("inputTokens", meter.cumulativeInputTokens()).param("cachedTokens", meter.cumulativeCachedInputTokens()).param("outputTokens", meter.cumulativeOutputTokens()).param("reasoningTokens", meter.cumulativeReasoningTokens()).param("providerCost", meter.meteredProviderCost()).param("creditCost", meter.meteredCreditCost()).update();
            jdbc.sql("update ai_usage.model_calls set status = 'RUNNING' where id = :id and tenant_id = :tenantId and status in ('UNKNOWN','PROVIDER_ACCEPTED','RUNNING')")
                    .param("id", meter.modelCallId()).param("tenantId", meter.tenantId()).update();
            return meter;
        });
    }

    @Override
    public ModelCallReceipt beginModelCall(ProductionRuntimeModels.ModelCallRequest request) {
        return inTenant(request.tenantId(), () -> {
            var existingCall = jdbc.sql("select id, status, provider_request_id from ai_usage.model_calls where tenant_id = :tenantId and idempotency_key = :key for update")
                    .param("tenantId", request.tenantId()).param("key", request.idempotencyKey())
                    .query((rs, row) -> new ExistingModelCall(rs.getObject("id", UUID.class), ModelCallStatus.valueOf(rs.getString("status")), rs.getString("provider_request_id"))).optional();
            if (existingCall.isPresent()) {
                var call = existingCall.get();
                var receipt = jdbc.sql("select request_hash, response_artifact_id from ai_usage.model_call_receipts where model_call_id = :id for update")
                        .param("id", call.id()).query((rs, row) -> new ExistingReceipt(rs.getString("request_hash"), rs.getString("response_artifact_id"))).optional()
                        .orElseThrow(() -> new ProductionRuntimeException("MODEL_CALL_RECEIPT_MISSING", "model call has no durable receipt"));
                var hash = receipt.requestHash();
                if (!hash.equals(request.requestHash())) throw new ProductionRuntimeException("MODEL_CALL_IDEMPOTENCY_CONFLICT", "model call key has a different request hash");
                if (call.status() == ModelCallStatus.UNKNOWN || call.status() == ModelCallStatus.PROVIDER_ACCEPTED) throw new ProductionRuntimeException("MODEL_CALL_RECONCILIATION_REQUIRED", "provider outcome must be reconciled before retry");
                return new ModelCallReceipt(call.id(), call.status(), call.providerRequestId(), receipt.responseArtifactId());
            }
            assertModelCallAdmission(request);
            UUID callId = UUID.randomUUID();
            jdbc.sql("""
                    insert into ai_usage.model_calls
                      (id, tenant_id, account_id, project_id, job_id, stage_id, work_item_id, attempt_id, provider, model, idempotency_key)
                    values (:id, :tenantId, :accountId, :projectId, :jobId, :stageId, :workItemId, :attemptId, :provider, :model, :key)
                    """).param("id", callId).param("tenantId", request.tenantId()).param("accountId", request.accountId()).param("projectId", request.projectId()).param("jobId", request.jobId()).param("stageId", request.stageId()).param("workItemId", request.workItemId()).param("attemptId", request.attemptId()).param("provider", request.provider()).param("model", request.model()).param("key", request.idempotencyKey()).update();
            jdbc.sql("insert into ai_usage.model_call_receipts (model_call_id, tenant_id, request_hash, receipt_state) values (:id, :tenantId, :hash, 'CREATED')")
                    .param("id", callId).param("tenantId", request.tenantId()).param("hash", request.requestHash()).update();
            return new ModelCallReceipt(callId, ModelCallStatus.CREATED, null, null);
        });
    }

    @Override
    public void claimProviderDispatch(UUID tenantId, UUID modelCallId) {
        inTenant(tenantId, () -> {
            int callChanged = jdbc.sql("""
                    update ai_usage.model_calls
                       set status = 'UNKNOWN'
                     where tenant_id = :tenantId and id = :id and status = 'CREATED'
                    """)
                    .param("tenantId", tenantId).param("id", modelCallId).update();
            if (callChanged != 1) {
                ModelCallState current = modelCallForUpdate(tenantId, modelCallId);
                throw new ProductionRuntimeException(
                        current == null ? "MODEL_CALL_NOT_FOUND" : "MODEL_CALL_RECONCILIATION_REQUIRED",
                        current == null
                                ? "model call does not exist for this tenant"
                                : "provider dispatch was already claimed and must not be sent again");
            }
            int receiptChanged = jdbc.sql("""
                    update ai_usage.model_call_receipts
                       set receipt_state = 'UNKNOWN',
                           last_provider_status = 'PROVIDER_SEND_CLAIMED',
                           next_reconcile_at = now() + interval '30 seconds',
                           updated_at = now()
                     where tenant_id = :tenantId and model_call_id = :id
                       and receipt_state = 'CREATED'
                    """)
                    .param("tenantId", tenantId).param("id", modelCallId).update();
            if (receiptChanged != 1) {
                throw new ProductionRuntimeException(
                        "MODEL_CALL_RECEIPT_STATE_CONFLICT",
                        "provider dispatch claim has no matching CREATED receipt");
            }
            return null;
        });
    }

    @Override
    public void markProviderAccepted(UUID tenantId, UUID modelCallId, String providerRequestId) {
        inTenant(tenantId, () -> {
            requireProviderRequestId(providerRequestId);
            ModelCallState current = requireModelCallForUpdate(tenantId, modelCallId);
            assertProviderRequestBinding(current, providerRequestId);
            if (current.status() == ModelCallStatus.PROVIDER_ACCEPTED
                    && "PROVIDER_ACCEPTED".equals(current.receiptState())) {
                return null;
            }
            if (current.status() != ModelCallStatus.UNKNOWN
                    || !"UNKNOWN".equals(current.receiptState())) {
                throw new ProductionRuntimeException(
                        "MODEL_CALL_STATE_CONFLICT",
                        "model call is not accepting a provider acknowledgement");
            }
            int updated = jdbc.sql("update ai_usage.model_calls set status = 'PROVIDER_ACCEPTED', provider_request_id = :providerRequestId where tenant_id = :tenantId and id = :id and status = 'UNKNOWN' and (provider_request_id is null or provider_request_id = :providerRequestId)")
                    .param("tenantId", tenantId).param("id", modelCallId).param("providerRequestId", providerRequestId).update();
            if (updated != 1) throw new ProductionRuntimeException("MODEL_CALL_STATE_CONFLICT", "model call is not accepting a provider acknowledgement");
            int receiptUpdated = jdbc.sql("update ai_usage.model_call_receipts set receipt_state = 'PROVIDER_ACCEPTED', provider_request_id = :providerRequestId, next_reconcile_at = now() + interval '30 seconds', updated_at = now() where tenant_id = :tenantId and model_call_id = :id and receipt_state = 'UNKNOWN' and (provider_request_id is null or provider_request_id = :providerRequestId)")
                    .param("tenantId", tenantId).param("id", modelCallId).param("providerRequestId", providerRequestId).update();
            if (receiptUpdated != 1) {
                throw new ProductionRuntimeException(
                        "MODEL_CALL_RECEIPT_STATE_CONFLICT",
                        "model call receipt did not accept the provider acknowledgement");
            }
            return null;
        });
    }

    @Override
    public void markProviderUnknown(UUID tenantId, UUID modelCallId, String providerStatus) {
        markProviderUnknown(tenantId, modelCallId, null, providerStatus);
    }

    @Override
    public void markProviderUnknown(
            UUID tenantId,
            UUID modelCallId,
            String providerRequestId,
            String providerStatus
    ) {
        inTenant(tenantId, () -> {
            if (providerRequestId != null) requireProviderRequestId(providerRequestId);
            ModelCallState current = requireModelCallForUpdate(tenantId, modelCallId);
            if (current.status() != ModelCallStatus.UNKNOWN
                    && current.status() != ModelCallStatus.PROVIDER_ACCEPTED
                    && current.status() != ModelCallStatus.RUNNING) {
                throw new ProductionRuntimeException(
                        "MODEL_CALL_STATE_CONFLICT",
                        "terminal or unclaimed model call cannot become uncertain");
            }
            assertProviderRequestBinding(current, providerRequestId);
            int callUpdated = jdbc.sql("update ai_usage.model_calls set status = 'UNKNOWN', provider_request_id = coalesce(:providerRequestId, provider_request_id) where tenant_id = :tenantId and id = :id and status in ('PROVIDER_ACCEPTED','RUNNING','UNKNOWN')")
                    .param("tenantId", tenantId).param("id", modelCallId)
                    .param("providerRequestId", providerRequestId).update();
            int receiptUpdated = jdbc.sql("update ai_usage.model_call_receipts set receipt_state = 'UNKNOWN', provider_request_id = coalesce(:providerRequestId, provider_request_id), last_provider_status = :status, reconcile_attempts = reconcile_attempts + 1, next_reconcile_at = now() + make_interval(secs => least(3600, 30 * power(2, least(reconcile_attempts, 7))::integer)), updated_at = now() where tenant_id = :tenantId and model_call_id = :id and receipt_state in ('PROVIDER_ACCEPTED','UNKNOWN')")
                    .param("tenantId", tenantId).param("id", modelCallId)
                    .param("providerRequestId", providerRequestId)
                    .param("status", boundedReason(providerStatus)).update();
            if (callUpdated != 1 || receiptUpdated != 1) {
                throw new ProductionRuntimeException(
                        "MODEL_CALL_STATE_CONFLICT",
                        "model call uncertainty transition did not update both durable records");
            }
            return null;
        });
    }

    @Override
    public void completeModelCall(UUID tenantId, UUID modelCallId, String providerRequestId, UUID responseArtifactId) {
        inTenant(tenantId, () -> {
            requireProviderRequestId(providerRequestId);
            if (responseArtifactId == null) {
                throw new IllegalArgumentException("provider completion requires a response artifact id");
            }
            ModelCallState current = requireModelCallForUpdate(tenantId, modelCallId);
            assertProviderRequestBinding(current, providerRequestId);
            if (current.status() == ModelCallStatus.COMPLETE) {
                if (providerRequestId.equals(current.callProviderRequestId())
                        && providerRequestId.equals(current.receiptProviderRequestId())
                        && responseArtifactId.equals(current.responseArtifactId())
                        && "COMPLETE".equals(current.receiptState())) {
                    return null;
                }
                throw new ProductionRuntimeException(
                        "MODEL_CALL_COMPLETION_CONFLICT",
                        "completed model call was replayed with different provider evidence");
            }
            if (current.status() != ModelCallStatus.UNKNOWN
                    && current.status() != ModelCallStatus.PROVIDER_ACCEPTED
                    && current.status() != ModelCallStatus.RUNNING) {
                throw new ProductionRuntimeException(
                        "MODEL_CALL_STATE_CONFLICT",
                        "model call is not ready for provider completion");
            }
            int updated = jdbc.sql("update ai_usage.model_calls set status = 'COMPLETE', provider_request_id = :providerRequestId, completed_at = now() where tenant_id = :tenantId and id = :id and status in ('PROVIDER_ACCEPTED','RUNNING','UNKNOWN')")
                    .param("tenantId", tenantId).param("id", modelCallId).param("providerRequestId", providerRequestId).update();
            if (updated != 1) throw new ProductionRuntimeException("MODEL_CALL_STATE_CONFLICT", "model call is not ready for provider completion");
            int receiptUpdated = jdbc.sql("update ai_usage.model_call_receipts set receipt_state = 'COMPLETE', provider_request_id = :providerRequestId, response_artifact_id = :artifactId, next_reconcile_at = null, updated_at = now() where tenant_id = :tenantId and model_call_id = :id and receipt_state in ('PROVIDER_ACCEPTED','UNKNOWN')")
                    .param("tenantId", tenantId).param("id", modelCallId).param("providerRequestId", providerRequestId).param("artifactId", responseArtifactId).update();
            if (receiptUpdated != 1) {
                throw new ProductionRuntimeException(
                        "MODEL_CALL_RECEIPT_STATE_CONFLICT",
                        "model call receipt is not ready for provider completion");
            }
            return null;
        });
    }

    @Override
    public void markProviderFailed(UUID tenantId, UUID modelCallId, String providerStatus) {
        inTenant(tenantId, () -> {
            ModelCallState current = requireModelCallForUpdate(tenantId, modelCallId);
            if (current.status() == ModelCallStatus.FAILED
                    && "FAILED".equals(current.receiptState())) return null;
            if (current.status() != ModelCallStatus.UNKNOWN
                    && current.status() != ModelCallStatus.PROVIDER_ACCEPTED
                    && current.status() != ModelCallStatus.RUNNING) {
                throw new ProductionRuntimeException(
                        "MODEL_CALL_STATE_CONFLICT",
                        "unclaimed or completed model call cannot become failed");
            }
            int updated = jdbc.sql("update ai_usage.model_calls set status = 'FAILED', completed_at = now() where tenant_id = :tenantId and id = :id and status in ('PROVIDER_ACCEPTED','RUNNING','UNKNOWN')")
                    .param("tenantId", tenantId).param("id", modelCallId).update();
            if (updated != 1) throw new ProductionRuntimeException("MODEL_CALL_STATE_CONFLICT", "model call is not ready for provider failure");
            int receiptUpdated = jdbc.sql("update ai_usage.model_call_receipts set receipt_state = 'FAILED', last_provider_status = :status, next_reconcile_at = null, updated_at = now() where tenant_id = :tenantId and model_call_id = :id and receipt_state in ('PROVIDER_ACCEPTED','UNKNOWN')")
                    .param("tenantId", tenantId).param("id", modelCallId).param("status", boundedReason(providerStatus)).update();
            if (receiptUpdated != 1) {
                throw new ProductionRuntimeException(
                        "MODEL_CALL_RECEIPT_STATE_CONFLICT",
                        "model call receipt is not ready for provider failure");
            }
            return null;
        });
    }

    @Override
    public TopUpResult applyVerifiedTopUp(TopUpRequest request) {
        return inTenant(request.tenantId(), () -> {
            String key = request.provider() + ":" + request.providerPaymentId();
            var existing = findIdempotency(request.tenantId(), TOP_UP_OPERATION, key);
            if (existing != null) {
                assertRequestHash(existing.requestHash(), request.requestHash());
                if (existing.state() != IdempotencyState.SUCCEEDED) throw new ProductionRuntimeException("TOP_UP_IN_PROGRESS", "top-up must be reconciled before retry");
                return topUpById(existing.resourceId());
            }
            insertIdempotency(request.tenantId(), TOP_UP_OPERATION, key, request.requestHash());
            UUID topUpId = UUID.randomUUID();
            jdbc.sql("insert into billing.topups (id, tenant_id, wallet_id, provider, provider_payment_id, amount, status, completed_at) values (:id, :tenantId, :walletId, :provider, :paymentId, :amount, 'COMPLETED', now())")
                    .param("id", topUpId).param("tenantId", request.tenantId()).param("walletId", request.walletId()).param("provider", request.provider()).param("paymentId", request.providerPaymentId()).param("amount", request.amount()).update();
            jdbc.sql("update billing.wallet_balances set available_balance = available_balance + :amount, version = version + 1, updated_at = now() where wallet_id = :walletId")
                    .param("amount", request.amount()).param("walletId", request.walletId()).update();
            ledgerAndJournal(request.tenantId(), request.walletId(), "TOPUP", topUpId, request.amount(), key);
            var result = topUpById(topUpId);
            completeIdempotency(request.tenantId(), TOP_UP_OPERATION, key, topUpId, result);
            outbox(request.tenantId(), "TOP_UP", topUpId, "TOPUP_COMPLETED", Map.of("amount", request.amount()));
            return result;
        });
    }

    @Override
    public int expireReservations(int limit) {
        int bounded = Math.max(1, Math.min(limit, 1_000));
        var candidates = jdbc.sql("select * from billing.expired_reservation_candidates(:limit)")
                .param("limit", bounded)
                .query((rs, row) -> new ExpiredReservation(
                        rs.getObject("tenant_id", UUID.class),
                        rs.getObject("reservation_id", UUID.class)))
                .list();
        int expired = 0;
        for (var candidate : candidates) {
            Boolean changed = inTenant(candidate.tenantId(), () -> {
                var reservation = jdbc.sql("""
                        select id, wallet_id, reserved_amount, consumed_amount, status
                          from billing.credit_reservations
                         where tenant_id = :tenantId and id = :id for update
                        """)
                        .param("tenantId", candidate.tenantId())
                        .param("id", candidate.reservationId())
                        .query((rs, row) -> new ReservationRow(
                                rs.getObject("id", UUID.class), rs.getObject("wallet_id", UUID.class),
                                rs.getBigDecimal("reserved_amount"), rs.getBigDecimal("consumed_amount"),
                                ReservationStatus.valueOf(rs.getString("status"))))
                        .optional().orElse(null);
                if (reservation == null || reservation.status() != ReservationStatus.ACTIVE) return false;
                BigDecimal unused = reservation.reservedAmount().subtract(reservation.consumedAmount());
                jdbc.sql("update billing.wallet_balances set available_balance = available_balance + :unused, reserved_balance = reserved_balance - :unused, version = version + 1, updated_at = now() where tenant_id = :tenantId and wallet_id = :walletId")
                        .param("unused", unused).param("tenantId", candidate.tenantId())
                        .param("walletId", reservation.walletId()).update();
                int updated = jdbc.sql("update billing.credit_reservations set status = 'EXPIRED', settled_at = now(), last_transition_reason = 'RESERVATION_TTL_EXPIRED' where tenant_id = :tenantId and id = :id and status = 'ACTIVE'")
                        .param("tenantId", candidate.tenantId()).param("id", candidate.reservationId()).update();
                if (updated == 1) outbox(candidate.tenantId(), "CREDIT_RESERVATION",
                        candidate.reservationId(), "CREDIT_RESERVATION_EXPIRED", Map.of("released", unused));
                return updated == 1;
            });
            if (Boolean.TRUE.equals(changed)) expired++;
        }
        return expired;
    }

    @Override
    public List<ProductionRuntimeModels.ModelCallRecoveryCandidate> uncertainModelCalls(int limit) {
        int bounded = Math.max(1, Math.min(limit, 1_000));
        return jdbc.sql("select * from ai_usage.uncertain_model_call_candidates(:limit)")
                .param("limit", bounded)
                .query((rs, row) -> {
                    var request = new ProductionRuntimeModels.ModelCallRequest(
                            rs.getObject("tenant_id", UUID.class),
                            rs.getObject("account_id", UUID.class),
                            rs.getObject("project_id", UUID.class),
                            rs.getObject("job_id", UUID.class),
                            rs.getObject("stage_id", UUID.class),
                            rs.getObject("work_item_id", UUID.class),
                            rs.getObject("attempt_id", UUID.class),
                            rs.getString("provider"), rs.getString("model"),
                            rs.getString("idempotency_key"), rs.getString("request_hash"));
                    return new ProductionRuntimeModels.ModelCallRecoveryCandidate(
                            rs.getObject("model_call_id", UUID.class), request,
                            rs.getString("provider_request_id"),
                            ModelCallStatus.valueOf(rs.getString("call_status")),
                            rs.getInt("reconcile_attempts"));
                }).list();
    }

    private ReservationResult reservationById(UUID id) {
        return jdbc.sql("select id, status, reserved_amount, wallet_id from billing.credit_reservations where id = :id")
                .param("id", id).query((rs, row) -> {
                    UUID walletId = rs.getObject("wallet_id", UUID.class);
                    BigDecimal available = jdbc.sql("select available_balance from billing.wallet_balances where wallet_id = :walletId").param("walletId", walletId).query(BigDecimal.class).single();
                    return new ReservationResult(rs.getObject("id", UUID.class), ReservationStatus.valueOf(rs.getString("status")), rs.getBigDecimal("reserved_amount"), available);
                }).single();
    }

    private TopUpResult topUpById(UUID id) {
        return jdbc.sql("select t.id, t.status, wb.available_balance from billing.topups t join billing.wallet_balances wb on wb.wallet_id = t.wallet_id where t.id = :id")
                .param("id", id).query((rs, row) -> new TopUpResult(rs.getObject("id", UUID.class), TopUpStatus.valueOf(rs.getString("status")), rs.getBigDecimal("available_balance"))).single();
    }

    private void validateFinalUsage(FinalUsage usage, BigDecimal reserved) {
        if (usage.inputTokens() < 0 || usage.cachedInputTokens() < 0 || usage.outputTokens() < 0 || usage.reasoningTokens() < 0 || usage.providerTotalCost().signum() < 0 || usage.customerCreditCost().signum() < 0) throw new ProductionRuntimeException("FINAL_USAGE_INVALID", "final usage values must be non-negative");
        if (usage.customerCreditCost().compareTo(reserved) > 0) throw new ProductionRuntimeException("FINAL_USAGE_EXCEEDS_RESERVATION", "final customer charge exceeds reserved credit");
    }

    private AdmissionLimits lockAdmission(UUID tenantId) {
        return jdbc.sql("""
                select max_concurrent_model_calls, max_provider_calls_per_minute,
                       daily_token_cap, daily_credit_cap
                  from orchestration.admission_policies
                 where tenant_id = :tenantId for update
                """).param("tenantId", tenantId)
                .query((rs, row) -> new AdmissionLimits(
                        rs.getInt("max_concurrent_model_calls"),
                        rs.getInt("max_provider_calls_per_minute"),
                        rs.getLong("daily_token_cap"),
                        rs.getBigDecimal("daily_credit_cap")))
                .optional().orElseThrow(() -> new ProductionRuntimeException(
                        "ADMISSION_POLICY_MISSING", "tenant has no durable admission policy"));
    }

    private void assertReservationAdmission(UUID tenantId, BigDecimal requested) {
        AdmissionLimits limits = lockAdmission(tenantId);
        BigDecimal committed = jdbc.sql("""
                select coalesce((select sum(customer_credit_cost)
                                  from billing.token_usage_events
                                 where tenant_id = :tenantId
                                   and created_at >= date_trunc('day', now())), 0)
                     + coalesce((select sum(reserved_amount)
                                  from billing.credit_reservations
                                 where tenant_id = :tenantId and status = 'ACTIVE'), 0)
                """).param("tenantId", tenantId).query(BigDecimal.class).single();
        if (committed.add(requested).compareTo(limits.dailyCreditCap()) > 0) {
            throw new ProductionRuntimeException(
                    "DAILY_CREDIT_CAP_EXCEEDED", "reservation exceeds the tenant daily credit cap");
        }
    }

    private void assertModelCallAdmission(ProductionRuntimeModels.ModelCallRequest request) {
        AdmissionLimits limits = lockAdmission(request.tenantId());
        long active = jdbc.sql("""
                select count(*) from ai_usage.model_calls
                 where tenant_id = :tenantId
                   and status in ('CREATED','PROVIDER_ACCEPTED','RUNNING','UNKNOWN')
                """).param("tenantId", request.tenantId()).query(Long.class).single();
        if (active >= limits.maxConcurrentModelCalls()) {
            throw new ProductionRuntimeException(
                    "MODEL_CALL_CONCURRENCY_EXHAUSTED", "tenant model-call concurrency is exhausted");
        }
        long recent = jdbc.sql("""
                select count(*) from ai_usage.model_calls
                 where tenant_id = :tenantId and provider = :provider
                   and created_at >= now() - interval '1 minute'
                """).param("tenantId", request.tenantId())
                .param("provider", request.provider()).query(Long.class).single();
        if (recent >= limits.maxProviderCallsPerMinute()) {
            throw new ProductionRuntimeException(
                    "PROVIDER_RATE_LIMIT_EXHAUSTED", "tenant provider-call rate is exhausted");
        }
    }

    private void assertMeterAdmission(MeterSnapshot meter) {
        AdmissionLimits limits = lockAdmission(meter.tenantId());
        DailyUsage used = jdbc.sql("""
                with final_usage as (
                    select coalesce(sum(input_tokens::numeric + output_tokens::numeric + reasoning_tokens::numeric), 0) tokens,
                           coalesce(sum(customer_credit_cost), 0) credits
                      from billing.token_usage_events
                     where tenant_id = :tenantId
                       and created_at >= date_trunc('day', now())
                ), latest_active as (
                    select distinct on (ume.model_call_id)
                           ume.model_call_id,
                           ume.cumulative_input_tokens::numeric + ume.cumulative_output_tokens::numeric
                             + ume.cumulative_reasoning_tokens::numeric tokens,
                           ume.metered_credit_cost credits
                      from billing.usage_meter_events ume
                      join ai_usage.model_calls mc
                        on mc.tenant_id = ume.tenant_id and mc.id = ume.model_call_id
                     where ume.tenant_id = :tenantId
                       and ume.model_call_id <> :modelCallId
                       and mc.status in ('CREATED','PROVIDER_ACCEPTED','RUNNING','UNKNOWN')
                     order by ume.model_call_id, ume.sequence_no desc
                )
                select f.tokens + coalesce(sum(a.tokens), 0),
                       f.credits + coalesce(sum(a.credits), 0)
                  from final_usage f left join latest_active a on true
                 group by f.tokens, f.credits
                """).param("tenantId", meter.tenantId())
                .param("modelCallId", meter.modelCallId())
                .query((rs, row) -> new DailyUsage(
                        rs.getBigDecimal(1), rs.getBigDecimal(2))).single();
        BigDecimal candidateTokens = BigDecimal.valueOf(meter.cumulativeInputTokens())
                .add(BigDecimal.valueOf(meter.cumulativeOutputTokens()))
                .add(BigDecimal.valueOf(meter.cumulativeReasoningTokens()));
        if (used.tokens().add(candidateTokens)
                .compareTo(BigDecimal.valueOf(limits.dailyTokenCap())) > 0) {
            throw new ProductionRuntimeException(
                    "DAILY_TOKEN_CAP_EXCEEDED", "meter exceeds the tenant daily token cap");
        }
        if (used.credits().add(meter.meteredCreditCost())
                .compareTo(limits.dailyCreditCap()) > 0) {
            throw new ProductionRuntimeException(
                    "DAILY_CREDIT_CAP_EXCEEDED", "meter exceeds the tenant daily credit cap");
        }
    }

    private void assertFinalUsageAdmission(FinalUsage usage) {
        AdmissionLimits limits = lockAdmission(usage.tenantId());
        DailyUsage used = jdbc.sql("""
                select coalesce(sum(input_tokens::numeric + output_tokens::numeric + reasoning_tokens::numeric), 0),
                       coalesce(sum(customer_credit_cost), 0)
                  from billing.token_usage_events
                 where tenant_id = :tenantId
                   and created_at >= date_trunc('day', now())
                """).param("tenantId", usage.tenantId())
                .query((rs, row) -> new DailyUsage(
                        rs.getBigDecimal(1), rs.getBigDecimal(2))).single();
        BigDecimal tokens = BigDecimal.valueOf(usage.inputTokens())
                .add(BigDecimal.valueOf(usage.outputTokens()))
                .add(BigDecimal.valueOf(usage.reasoningTokens()));
        if (used.tokens().add(tokens)
                .compareTo(BigDecimal.valueOf(limits.dailyTokenCap())) > 0) {
            throw new ProductionRuntimeException(
                    "DAILY_TOKEN_CAP_EXCEEDED", "final usage exceeds the tenant daily token cap");
        }
        if (used.credits().add(usage.customerCreditCost())
                .compareTo(limits.dailyCreditCap()) > 0) {
            throw new ProductionRuntimeException(
                    "DAILY_CREDIT_CAP_EXCEEDED", "final usage exceeds the tenant daily credit cap");
        }
    }

    private void validateUsageBindingsAndPricing(FinalUsage usage) {
        long bound = jdbc.sql("""
                select count(*)
                  from ai_usage.model_calls mc
                  join ai_usage.model_call_receipts receipt
                    on receipt.tenant_id = mc.tenant_id
                   and receipt.model_call_id = mc.id
                  join billing.credit_reservations cr
                    on cr.tenant_id = mc.tenant_id
                   and cr.work_item_id = mc.work_item_id
                 where mc.tenant_id = :tenantId
                   and mc.id = :modelCallId
                   and cr.id = :reservationId
                   and mc.provider = :provider
                   and mc.model = :model
                   and mc.status = 'COMPLETE'
                   and receipt.receipt_state = 'COMPLETE'
                   and receipt.provider_request_id is not null
                   and receipt.response_artifact_id is not null
                """)
                .param("tenantId", usage.tenantId())
                .param("modelCallId", usage.modelCallId())
                .param("reservationId", usage.reservationId())
                .param("provider", usage.provider())
                .param("model", usage.model())
                .query(Long.class).single();
        if (bound != 1) {
            throw new ProductionRuntimeException(
                    "FINAL_USAGE_OWNERSHIP_MISMATCH",
                    "usage requires one tenant-owned reservation and a completed, artifact-backed provider call");
        }

        PriceTuple providerPrice = jdbc.sql("""
                select p.input_per_million, p.cached_input_per_million,
                       p.output_per_million, p.reasoning_per_million
                  from billing.provider_pricing_versions v
                  join billing.provider_model_prices p
                    on p.pricing_version_id = v.id
                  join ai_usage.model_calls mc
                    on mc.tenant_id = :tenantId and mc.id = :modelCallId
                 where v.id = :versionId
                   and p.provider = :provider
                   and p.model = :model
                   and v.effective_from <= mc.created_at
                   and (v.effective_to is null or v.effective_to > mc.created_at)
                """)
                .param("versionId", usage.providerPricingVersionId())
                .param("tenantId", usage.tenantId())
                .param("modelCallId", usage.modelCallId())
                .param("provider", usage.provider()).param("model", usage.model())
                .query((rs, row) -> new PriceTuple(
                        rs.getBigDecimal("input_per_million"),
                        rs.getBigDecimal("cached_input_per_million"),
                        rs.getBigDecimal("output_per_million"),
                        rs.getBigDecimal("reasoning_per_million")))
                .optional().orElseThrow(() -> new ProductionRuntimeException(
                        "PROVIDER_PRICE_NOT_EFFECTIVE",
                        "no exact effective provider/model price exists"));
        PriceTuple commercialPrice = jdbc.sql("""
                select p.credit_per_input_million, p.credit_per_cached_million,
                       p.credit_per_output_million, p.credit_per_reasoning_million
                  from billing.commercial_pricing_versions v
                  join billing.commercial_model_prices p
                    on p.pricing_version_id = v.id
                  join ai_usage.model_calls mc
                    on mc.tenant_id = :tenantId and mc.id = :modelCallId
                 where v.id = :versionId
                   and p.provider = :provider
                   and p.model = :model
                   and v.effective_from <= mc.created_at
                   and (v.effective_to is null or v.effective_to > mc.created_at)
                """)
                .param("versionId", usage.commercialPricingVersionId())
                .param("tenantId", usage.tenantId())
                .param("modelCallId", usage.modelCallId())
                .param("provider", usage.provider()).param("model", usage.model())
                .query((rs, row) -> new PriceTuple(
                        rs.getBigDecimal("credit_per_input_million"),
                        rs.getBigDecimal("credit_per_cached_million"),
                        rs.getBigDecimal("credit_per_output_million"),
                        rs.getBigDecimal("credit_per_reasoning_million")))
                .optional().orElseThrow(() -> new ProductionRuntimeException(
                        "COMMERCIAL_PRICE_NOT_EFFECTIVE",
                        "no exact effective commercial provider/model price exists"));
        if (price(providerPrice, usage).compareTo(usage.providerTotalCost()) != 0
                || price(commercialPrice, usage).compareTo(usage.customerCreditCost()) != 0) {
            throw new ProductionRuntimeException(
                    "FINAL_USAGE_PRICE_MISMATCH",
                    "supplied final totals do not equal the immutable pricing versions");
        }

        jdbc.sql("""
                select sequence_no, cumulative_input_tokens,
                       cumulative_cached_input_tokens, cumulative_output_tokens,
                       cumulative_reasoning_tokens, metered_provider_cost,
                       metered_credit_cost
                  from billing.usage_meter_events
                 where tenant_id = :tenantId and model_call_id = :modelCallId
                 order by sequence_no desc limit 1
                """)
                .param("tenantId", usage.tenantId())
                .param("modelCallId", usage.modelCallId())
                .query((rs, row) -> new MeterValues(
                        rs.getLong("sequence_no"), rs.getLong("cumulative_input_tokens"),
                        rs.getLong("cumulative_cached_input_tokens"),
                        rs.getLong("cumulative_output_tokens"),
                        rs.getLong("cumulative_reasoning_tokens"),
                        rs.getBigDecimal("metered_provider_cost"),
                        rs.getBigDecimal("metered_credit_cost")))
                .optional().ifPresent(meter -> {
                    if (meter.inputTokens() > usage.inputTokens()
                            || meter.cachedTokens() > usage.cachedInputTokens()
                            || meter.outputTokens() > usage.outputTokens()
                            || meter.reasoningTokens() > usage.reasoningTokens()
                            || meter.providerCost().compareTo(usage.providerTotalCost()) > 0
                            || meter.creditCost().compareTo(usage.customerCreditCost()) > 0) {
                        throw new ProductionRuntimeException(
                                "FINAL_USAGE_BELOW_STREAM_METER",
                                "final usage cannot move below a committed cumulative meter");
                    }
                });
    }

    private static BigDecimal price(PriceTuple price, FinalUsage usage) {
        BigDecimal total = price.input().multiply(BigDecimal.valueOf(usage.inputTokens()))
                .add(price.cached().multiply(BigDecimal.valueOf(usage.cachedInputTokens())))
                .add(price.output().multiply(BigDecimal.valueOf(usage.outputTokens())))
                .add(price.reasoning().multiply(BigDecimal.valueOf(usage.reasoningTokens())))
                .divide(BigDecimal.valueOf(1_000_000L), 12, java.math.RoundingMode.HALF_UP);
        return ProductionRuntimeModels.canonicalMoney(total);
    }

    private void ledgerAndJournal(UUID tenantId, UUID walletId, String entryType, UUID referenceId, BigDecimal amount, String idempotencyKey) {
        if (amount.signum() == 0) return;
        jdbc.sql("insert into billing.ledger_entries (id, tenant_id, wallet_id, entry_type, reference_type, reference_id, amount, idempotency_key) values (:id, :tenantId, :walletId, :entryType, 'BILLING', :referenceId, :amount, :key)")
                .param("id", UUID.randomUUID()).param("tenantId", tenantId).param("walletId", walletId).param("entryType", entryType).param("referenceId", referenceId).param("amount", entryType.equals("USAGE") ? amount.negate() : amount).param("key", idempotencyKey).update();
        UUID journalId = UUID.randomUUID();
        jdbc.sql("insert into billing.billing_journals (id, tenant_id, journal_type, reference_type, reference_id, idempotency_key, memo) values (:id, :tenantId, :type, 'BILLING', :referenceId, :key, :memo)")
                .param("id", journalId).param("tenantId", tenantId).param("type", entryType).param("referenceId", referenceId).param("key", "journal:" + idempotencyKey).param("memo", entryType).update();
        boolean usage = entryType.equals("USAGE");
        String currency = jdbc.sql("select currency from billing.wallets where id = :walletId and tenant_id = :tenantId")
                .param("walletId", walletId).param("tenantId", tenantId).query(String.class).single();
        if (usage) {
            journalLine(tenantId, journalId, "CUSTOMER_WALLET", currency, amount, BigDecimal.ZERO, walletId);
            journalLine(tenantId, journalId, "PLATFORM_REVENUE", currency, BigDecimal.ZERO, amount, walletId);
        } else {
            journalLine(tenantId, journalId, "CASH_CLEARING", currency, amount, BigDecimal.ZERO, walletId);
            journalLine(tenantId, journalId, "CUSTOMER_WALLET", currency, BigDecimal.ZERO, amount, walletId);
        }
    }

    private void journalLine(UUID tenantId, UUID journalId, String account, String currency, BigDecimal debit, BigDecimal credit, UUID walletId) {
        jdbc.sql("insert into billing.billing_journal_lines (tenant_id, journal_id, account_code, currency, debit, credit, wallet_id) values (:tenantId, :journalId, :account, :currency, :debit, :credit, :walletId)")
                .param("tenantId", tenantId).param("journalId", journalId).param("account", account).param("currency", currency).param("debit", debit).param("credit", credit).param("walletId", walletId).update();
    }

    private void outbox(UUID tenantId, String aggregateType, UUID aggregateId, String eventType, Map<String, Object> payload) {
        try {
            jdbc.sql("insert into observability.outbox_events (tenant_id, aggregate_type, aggregate_id, event_type, payload) values (:tenantId, :aggregateType, :aggregateId, :eventType, cast(:payload as jsonb))")
                    .param("tenantId", tenantId).param("aggregateType", aggregateType).param("aggregateId", aggregateId).param("eventType", eventType).param("payload", json.writeValueAsString(payload)).update();
        } catch (Exception ex) {
            throw new ProductionRuntimeException("OUTBOX_SERIALIZATION_FAILED", "could not serialize outbox payload", ex);
        }
    }

    private IdempotencyRow findIdempotency(UUID tenantId, String operation, String key) {
        return jdbc.sql("select request_hash, state, resource_id from billing.idempotency_records where tenant_id = :tenantId and operation_type = :operation and idempotency_key = :key for update")
                .param("tenantId", tenantId).param("operation", operation).param("key", key).query((rs, row) -> new IdempotencyRow(rs.getString("request_hash"), IdempotencyState.valueOf(rs.getString("state")), rs.getObject("resource_id", UUID.class))).optional().orElse(null);
    }

    private void insertIdempotency(UUID tenantId, String operation, String key, String requestHash) {
        jdbc.sql("insert into billing.idempotency_records (tenant_id, operation_type, idempotency_key, request_hash, state, expires_at) values (:tenantId, :operation, :key, :hash, 'IN_PROGRESS', now() + interval '24 hours')")
                .param("tenantId", tenantId).param("operation", operation).param("key", key).param("hash", requestHash).update();
    }

    private void completeIdempotency(UUID tenantId, String operation, String key, UUID resourceId, Object response) {
        try {
            jdbc.sql("update billing.idempotency_records set state = 'SUCCEEDED', resource_id = :resourceId, response_json = cast(:response as jsonb), completed_at = now() where tenant_id = :tenantId and operation_type = :operation and idempotency_key = :key")
                    .param("tenantId", tenantId).param("operation", operation).param("key", key).param("resourceId", resourceId).param("response", json.writeValueAsString(response)).update();
        } catch (Exception ex) { throw new ProductionRuntimeException("IDEMPOTENCY_RESPONSE_SERIALIZATION_FAILED", "could not persist idempotency response", ex); }
    }

    private void failIdempotency(UUID tenantId, String operation, String key, String error) {
        jdbc.sql("update billing.idempotency_records set state = 'FAILED', last_error = :error, completed_at = now() where tenant_id = :tenantId and operation_type = :operation and idempotency_key = :key")
                .param("tenantId", tenantId).param("operation", operation).param("key", key).param("error", error).update();
    }

    private void assertRequestHash(String stored, String incoming) {
        if (!Objects.equals(stored, incoming)) throw new ProductionRuntimeException("IDEMPOTENCY_CONFLICT", "idempotency key was reused with a different request");
    }

    private ModelCallState requireModelCallForUpdate(UUID tenantId, UUID modelCallId) {
        ModelCallState state = modelCallForUpdate(tenantId, modelCallId);
        if (state == null) {
            throw new ProductionRuntimeException(
                    "MODEL_CALL_NOT_FOUND", "model call does not exist for this tenant");
        }
        return state;
    }

    private ModelCallState modelCallForUpdate(UUID tenantId, UUID modelCallId) {
        return jdbc.sql("""
                select mc.status,
                       mc.provider_request_id as call_provider_request_id,
                       receipt.provider_request_id as receipt_provider_request_id,
                       receipt.response_artifact_id,
                       receipt.receipt_state
                  from ai_usage.model_calls mc
                  join ai_usage.model_call_receipts receipt
                    on receipt.tenant_id = mc.tenant_id
                   and receipt.model_call_id = mc.id
                 where mc.tenant_id = :tenantId and mc.id = :id
                 for update of mc, receipt
                """)
                .param("tenantId", tenantId).param("id", modelCallId)
                .query((rs, row) -> new ModelCallState(
                        ModelCallStatus.valueOf(rs.getString("status")),
                        rs.getString("call_provider_request_id"),
                        rs.getString("receipt_provider_request_id"),
                        rs.getObject("response_artifact_id", UUID.class),
                        rs.getString("receipt_state")))
                .optional().orElse(null);
    }

    private static void requireProviderRequestId(String providerRequestId) {
        if (providerRequestId == null
                || !providerRequestId.matches("[A-Za-z0-9._:-]{1,500}")) {
            throw new IllegalArgumentException("providerRequestId is malformed");
        }
    }

    private static void assertProviderRequestBinding(
            ModelCallState current,
            String providerRequestId
    ) {
        if (providerRequestId == null) return;
        if ((current.callProviderRequestId() != null
                && !providerRequestId.equals(current.callProviderRequestId()))
                || (current.receiptProviderRequestId() != null
                && !providerRequestId.equals(current.receiptProviderRequestId()))) {
            throw new ProductionRuntimeException(
                    "MODEL_CALL_PROVIDER_ID_CONFLICT",
                    "model call is already bound to a different provider request");
        }
    }

    private <T> T inTenant(UUID tenantId, java.util.function.Supplier<T> body) {
        Objects.requireNonNull(tenantId, "tenantId");
        return transactions.execute(status -> {
            jdbc.sql("select set_config('app.tenant_id', :tenantId, true)").param("tenantId", tenantId.toString()).query(String.class).single();
            return body.get();
        });
    }

    private static String hash(String value) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8))); }
        catch (Exception ex) { throw new IllegalStateException(ex); }
    }

    private static String boundedReason(String reason) { return reason == null || reason.isBlank() ? "UNSPECIFIED" : reason.substring(0, Math.min(reason.length(), 500)); }
    private static boolean sameMeter(MeterSnapshot left, MeterSnapshot right) {
        return left.tenantId().equals(right.tenantId())
                && left.reservationId().equals(right.reservationId())
                && left.modelCallId().equals(right.modelCallId())
                && left.sequenceNo() == right.sequenceNo()
                && left.cumulativeInputTokens() == right.cumulativeInputTokens()
                && left.cumulativeCachedInputTokens() == right.cumulativeCachedInputTokens()
                && left.cumulativeOutputTokens() == right.cumulativeOutputTokens()
                && left.cumulativeReasoningTokens() == right.cumulativeReasoningTokens()
                && left.meteredProviderCost().compareTo(right.meteredProviderCost()) == 0
                && left.meteredCreditCost().compareTo(right.meteredCreditCost()) == 0;
    }
    private record Balance(BigDecimal available, BigDecimal reserved) {}
    private record ReservationRow(UUID id, UUID walletId, BigDecimal reservedAmount, BigDecimal consumedAmount, ReservationStatus status) {}
    private record IdempotencyRow(String requestHash, IdempotencyState state, UUID resourceId) {}
    private record ExistingUsage(UUID modelCallId, BigDecimal amount) {}
    private record PriceTuple(BigDecimal input, BigDecimal cached, BigDecimal output, BigDecimal reasoning) {}
    private record MeterValues(long sequenceNo, long inputTokens, long cachedTokens, long outputTokens, long reasoningTokens, BigDecimal providerCost, BigDecimal creditCost) {}
    private record AdmissionLimits(
            int maxConcurrentModelCalls,
            int maxProviderCallsPerMinute,
            long dailyTokenCap,
            BigDecimal dailyCreditCap
    ) {}
    private record DailyUsage(BigDecimal tokens, BigDecimal credits) {}
    private record ExistingModelCall(UUID id, ModelCallStatus status, String providerRequestId) {}
    private record ExistingReceipt(String requestHash, String responseArtifactId) {}
    private record ModelCallState(
            ModelCallStatus status,
            String callProviderRequestId,
            String receiptProviderRequestId,
            UUID responseArtifactId,
            String receiptState
    ) {}
    private record ExpiredReservation(UUID tenantId, UUID reservationId) {}
}
