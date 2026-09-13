package io.elmos.commercial;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Optional;

/** Tenant-bound purchasing and generation-funding persistence boundary. */
public interface CommercialOrderPort {
    record Order(
            String orderId, String organizationId, String actorId, String orderType,
            String sku, String catalogVersion, String projectId, String currency,
            BigDecimal amountMinor, BigDecimal creditQuantity, String provider,
            String outTradeNo, String status, Instant createdAt, Instant expiresAt,
            Instant paidAt, Instant fulfilledAt, String failureCode
    ) {}

    record CreditBalance(String organizationId, BigDecimal balance,
                         BigDecimal reserved, BigDecimal spendable, String status) {}

    record CreditLedgerEntry(
            String ledgerEntryId, String actorId, String direction, BigDecimal quantity,
            BigDecimal balanceAfter, String entryType, String sourceOrderId,
            String projectId, String jobId, Instant expiresAt, Instant occurredAt
    ) {}

    record CreditReconciliation(
            String organizationId, BigDecimal projectedBalance, BigDecimal journalBalance,
            BigDecimal projectedReserved, BigDecimal journalReserved,
            BigDecimal balanceDrift, BigDecimal reservedDrift, long unbalancedTransactions
    ) {
        public boolean drifted() {
            return balanceDrift.signum() != 0 || reservedDrift.signum() != 0
                    || unbalancedTransactions != 0;
        }
    }

    record GenerationReservation(
            String reservationId, String decision, String fundingSource,
            BigDecimal remainingCredits
    ) {}

    String createOrder(String orderId, String organizationId, String actorId,
                       String sku, String projectId, String provider, String outTradeNo,
                       String idempotencyKey, String requestHash, int ttlSeconds);

    Optional<Order> findOrder(String organizationId, String orderId);

    String markOrderAwaitingPayment(String organizationId, String actorId, String orderId);

    String markOrderPreparationFailed(String organizationId, String actorId, String orderId,
                                      boolean outcomeUnknown, String failureCode);

    List<Order> orders(String organizationId, String actorId, int limit, int offset,
                       boolean organizationScope);

    CreditBalance creditBalance(String organizationId);

    List<CreditLedgerEntry> creditLedger(String organizationId, String actorId,
                                         int limit, int offset, boolean organizationScope);

    CreditReconciliation creditReconciliation(String organizationId);

    GenerationReservation reserveGeneration(String reservationId, String organizationId,
                                            String actorId, String projectId, String jobId,
                                            BigDecimal requestedCredits,
                                            String idempotencyKey, int ttlSeconds);

    String settleGeneration(String organizationId, String actorId,
                            String reservationId, BigDecimal actualCredits);

    String releaseGeneration(String organizationId, String actorId, String reservationId);
}
