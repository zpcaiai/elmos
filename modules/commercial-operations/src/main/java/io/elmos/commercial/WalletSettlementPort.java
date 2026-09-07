package io.elmos.commercial;

import java.math.BigDecimal;
import java.util.List;

/**
 * The cross-tenant half of the wallet: resolving holds after jobs finish.
 *
 * <p>Separate from {@link WalletPort} because the caller is different in kind.
 * {@code WalletPort} serves a request that already knows whose money it is;
 * this one is a background loop that discovers that from the outbox. Keeping
 * them apart means the tenant-facing surface cannot accidentally be handed a
 * method that iterates other tenants' work.
 */
public interface WalletSettlementPort {

    /** One unresolved settlement, leased to this settler for a bounded time. */
    record Claim(
            String outboxId,
            String organizationId,
            String jobId,
            String reservationId,
            String jobStatus,
            String failureCode,
            int attempts
    ) {}

    /** What the job actually did, which is what it should be priced on. */
    record JobFacts(
            String status,
            String failureCode,
            String businessLine,
            String jobKind,
            int budgetWallSeconds,
            int elapsedSeconds,
            boolean chargeableFailure
    ) {}

    /** The published price this job was quoted against. */
    record Quote(
            String quoteRef,
            BigDecimal reserveMinor,
            BigDecimal minChargeMinor,
            String unit,
            BigDecimal unitPriceMinor
    ) {}

    List<Claim> claim(int limit, int leaseSeconds);

    JobFacts facts(String organizationId, String jobId);

    Quote quote(String businessLine, String jobKind, int budgetWallSeconds);

    /**
     * Resolves one claim. A zero amount releases rather than charging zero.
     *
     * @return false when the claim was already resolved, which a retry must
     *         treat as success rather than as work still to do
     */
    boolean resolve(String outboxId, BigDecimal settledAmountMinor,
                    String resolutionCode, String actorId);

    /** Releases the lease and records why, so the next pass retries it. */
    void fail(String outboxId, String errorCode);
}
