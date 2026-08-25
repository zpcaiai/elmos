package io.elmos.commercial;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Optional;

/**
 * Persistence boundary for the prepaid wallet.
 *
 * <p>Every method takes the organization explicitly rather than reading it from
 * an ambient context. Two of the callers cannot have one: a payment callback
 * arrives before the tenant is known, and the settlement sweeper runs across
 * tenants. Making the parameter mandatory everywhere keeps one shape instead of
 * two, and matches the V73 functions, which bind the tenant they are given and
 * restore the previous binding afterwards.
 *
 * <p>The adapter never computes a balance. Balances move only inside the V73
 * accounting functions, which hold the wallet row lock and write the ledger in
 * the same statement -- an adapter that did arithmetic of its own would be a
 * second source of truth for money.
 */
public interface WalletPort {

    /**
     * A refusal that carries the machine-readable code the database raised.
     *
     * <p>Separate from {@code BillingStateException} on purpose: wallet refusals
     * are mostly expected outcomes a caller should translate into an HTTP status
     * (insufficient balance is a 402, not a 500), while a billing state error
     * usually means a broken assumption.
     */
    final class WalletStateException extends RuntimeException {
        private final String code;

        public WalletStateException(String code, String message) {
            super(message);
            this.code = code;
        }

        public WalletStateException(String code, String message, Throwable cause) {
            super(message, cause);
            this.code = code;
        }

        public String code() {
            return code;
        }
    }

    /** Spendable is balance minus held, and is the only figure a caller should gate on. */
    record WalletBalance(
            String organizationId,
            String currency,
            BigDecimal balanceMinor,
            BigDecimal reservedMinor,
            BigDecimal spendableMinor,
            String status,
            Instant updatedAt
    ) {}

    record LedgerEntry(
            String entryId,
            long seq,
            String direction,
            BigDecimal amountMinor,
            BigDecimal balanceAfterMinor,
            String entryType,
            String sourceType,
            String sourceRef,
            String actorId,
            String reason,
            Instant occurredAt
    ) {}

    record TopupOrder(
            String topupOrderId,
            String organizationId,
            String actorId,
            String currency,
            BigDecimal amountMinor,
            String provider,
            String outTradeNo,
            String status,
            Instant createdAt,
            Instant paidAt,
            Instant creditedAt,
            Instant expiresAt
    ) {}

    /** Per-tenant top-up bounds, resolved from the override table or the defaults. */
    record TopupBounds(
            BigDecimal minAmountMinor,
            BigDecimal maxAmountMinor,
            BigDecimal dailyAmountLimitMinor
    ) {}

    /**
     * The minimal cross-tenant projection a payment callback uses to find out
     * whose money it is holding, before any tenant context exists.
     */
    record TopupDirectoryEntry(
            String outTradeNo,
            String topupOrderId,
            String organizationId,
            BigDecimal amountMinor,
            String status
    ) {}

    WalletBalance balance(String organizationId);

    List<LedgerEntry> ledger(String organizationId, int limit, int offset);

    TopupBounds topupBounds(String organizationId);

    /**
     * Opens a top-up order. Amount bounds and the daily cap are enforced inside
     * the database function, so a caller cannot skip them by calling this from
     * somewhere new.
     *
     * @return the order id; a replayed idempotency key returns the original one
     */
    String createTopupOrder(String topupOrderId, String organizationId, String actorId,
                            BigDecimal amountMinor, String provider, String outTradeNo,
                            String idempotencyKey, int ttlSeconds);

    Optional<TopupOrder> findTopupOrder(String organizationId, String topupOrderId);

    /** Resolution for the callback path. No tenant context required. */
    Optional<TopupDirectoryEntry> findTopupByOutTradeNo(String outTradeNo);

    /**
     * Credits a confirmed top-up exactly once.
     *
     * @return the ledger entry id; a replay returns the entry the first call made
     */
    String creditTopup(String organizationId, String topupOrderId,
                       String providerTxnRef, String actorId);

    /** Holds money for a job. Refuses with {@code ELMOS_WALLET_INSUFFICIENT_BALANCE}. */
    String reserve(String reservationId, String organizationId, String jobId,
                   BigDecimal amountMinor, String quoteRef, String actorId, int ttlSeconds);

    /** Charges at most what was held; the database clamps an over-quote. */
    void settle(String organizationId, String jobId, BigDecimal settledAmountMinor,
                String actorId, String resolutionCode);

    void release(String organizationId, String jobId, String resolutionCode);

    int expireReservations(String organizationId, int limit);

    /** Administrator correction. A blank reason is refused by the database. */
    String adjust(String organizationId, String direction, BigDecimal amountMinor,
                  String actorId, String reason, String idempotencyKey);

    /**
     * Drift between the materialized wallet and its ledger. Both figures should
     * be zero; a non-zero result is an incident, not something to repair silently.
     */
    record Reconciliation(
            String organizationId,
            BigDecimal projectedBalanceMinor,
            BigDecimal ledgerBalanceMinor,
            BigDecimal projectedReservedMinor,
            BigDecimal heldReservedMinor
    ) {
        public boolean drifted() {
            return projectedBalanceMinor.compareTo(ledgerBalanceMinor) != 0
                    || projectedReservedMinor.compareTo(heldReservedMinor) != 0;
        }
    }

    Optional<Reconciliation> reconcile(String organizationId);
}
