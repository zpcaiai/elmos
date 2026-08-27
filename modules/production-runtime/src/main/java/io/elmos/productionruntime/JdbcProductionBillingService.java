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
            jdbc.sql("update ai_usage.model_calls set status = 'RUNNING' where id = :id and tenant_id = :tenantId and status in ('CREATED','PROVIDER_ACCEPTED')")
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
    public void markProviderAccepted(UUID tenantId, UUID modelCallId, String providerRequestId) {
        inTenant(tenantId, () -> {
            if (providerRequestId == null || providerRequestId.isBlank() || providerRequestId.length() > 500) throw new IllegalArgumentException("providerRequestId is required");
            int updated = jdbc.sql("update ai_usage.model_calls set status = 'PROVIDER_ACCEPTED', provider_request_id = :providerRequestId where tenant_id = :tenantId and id = :id and status in ('CREATED','PROVIDER_ACCEPTED')")
                    .param("tenantId", tenantId).param("id", modelCallId).param("providerRequestId", providerRequestId).update();
            if (updated != 1) throw new ProductionRuntimeException("MODEL_CALL_STATE_CONFLICT", "model call is not accepting a provider acknowledgement");
            jdbc.sql("update ai_usage.model_call_receipts set receipt_state = 'PROVIDER_ACCEPTED', provider_request_id = :providerRequestId, updated_at = now() where tenant_id = :tenantId and model_call_id = :id")
                    .param("tenantId", tenantId).param("id", modelCallId).param("providerRequestId", providerRequestId).update();
            return null;
        });
    }

    @Override
    public void markProviderUnknown(UUID tenantId, UUID modelCallId, String providerStatus) {
        inTenant(tenantId, () -> {
            jdbc.sql("update ai_usage.model_calls set status = 'UNKNOWN' where tenant_id = :tenantId and id = :id and status in ('CREATED','PROVIDER_ACCEPTED','RUNNING')")
                    .param("tenantId", tenantId).param("id", modelCallId).update();
            jdbc.sql("update ai_usage.model_call_receipts set receipt_state = 'UNKNOWN', last_provider_status = :status, updated_at = now() where tenant_id = :tenantId and model_call_id = :id")
                    .param("tenantId", tenantId).param("id", modelCallId).param("status", boundedReason(providerStatus)).update();
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
        journalLine(tenantId, journalId, usage ? "PLATFORM_REVENUE" : "CASH_CLEARING", currency, amount, BigDecimal.ZERO, walletId);
        journalLine(tenantId, journalId, "CUSTOMER_WALLET", currency, BigDecimal.ZERO, amount, walletId);
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
    private record MeterValues(long sequenceNo, long inputTokens, long cachedTokens, long outputTokens, long reasoningTokens, BigDecimal providerCost, BigDecimal creditCost) {}
    private record ExistingModelCall(UUID id, ModelCallStatus status, String providerRequestId) {}
    private record ExistingReceipt(String requestHash, String responseArtifactId) {}
}
