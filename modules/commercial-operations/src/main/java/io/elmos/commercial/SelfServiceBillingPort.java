package io.elmos.commercial;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

/**
 * Tenant-scoped persistence boundary for self-service billing and usage.
 *
 * <p>Every method receives the organization derived from authenticated identity.
 * Adapters must bind that value to the database transaction before executing any
 * tenant query. Client-supplied organization identifiers are not accepted.</p>
 */
public interface SelfServiceBillingPort {
    final class BillingStateException extends RuntimeException {
        private final String code;

        public BillingStateException(String code, String message) {
            super(message);
            this.code = code;
        }

        public String code() {
            return code;
        }
    }

    record QuotaMeasure(
            BigDecimal consumed,
            BigDecimal reserved,
            BigDecimal limit,
            BigDecimal remaining,
            int usageBps,
            boolean hardStop
    ) {}

    record UsageSnapshot(
            String schemaVersion,
            String status,
            String organizationId,
            String actorId,
            String subscriptionId,
            String planId,
            String displayName,
            String allowanceWindow,
            Instant periodStartsAt,
            Instant periodEndsAt,
            Instant resetsAt,
            QuotaMeasure tokens,
            QuotaMeasure credits,
            long reconciledEventCount,
            long unreconciledEventCount,
            Instant eventWatermark,
            Instant generatedAt,
            int refreshAfterSeconds
    ) {}

    record UsageHistoryPoint(
            Instant bucketStartsAt,
            String meterId,
            String operationKey,
            String tokenClass,
            String actorId,
            String provider,
            BigDecimal debited,
            BigDecimal credited,
            BigDecimal net
    ) {}

    record UsageReservation(
            String reservationId,
            String decision,
            BigDecimal remainingTokens,
            BigDecimal remainingCredits
    ) {}

    record UsageSettlement(
            String reservationId,
            String status,
            BigDecimal consumedTokens,
            BigDecimal consumedCredits,
            BigDecimal remainingTokens,
            BigDecimal remainingCredits
    ) {}

    record AlertPreference(
            String preferenceId,
            String actorId,
            String scope,
            List<Integer> thresholdBps,
            boolean emailEnabled,
            boolean inAppEnabled,
            long version
    ) {
        public AlertPreference {
            thresholdBps = List.copyOf(thresholdBps);
        }
    }

    record UsageAlert(
            String alertId,
            String meterId,
            int thresholdBps,
            String channel,
            String status,
            Instant occurredAt
    ) {}

    record TrialGrant(
            String trialGrantId,
            String subscriptionId,
            String planId,
            Instant startsAt,
            Instant endsAt,
            String status
    ) {}

    record CheckoutRecord(
            String checkoutSessionId,
            String planId,
            String catalogVersion,
            String currency,
            BigDecimal amountMinor,
            String providerSessionRef,
            String checkoutUrl,
            String status,
            Instant expiresAt
    ) {}

    record SubscriptionBinding(
            String subscriptionId,
            String planId,
            String status,
            String provider,
            String providerSubscriptionRef,
            Instant currentPeriodEnd,
            boolean cancelAtPeriodEnd
    ) {}

    record ProviderEvent(
            String eventId,
            String eventType,
            String objectRef,
            String subscriptionRef,
            String customerRef,
            String invoiceRef,
            BigDecimal amountMinor,
            String currency,
            Instant eventCreatedAt,
            String payloadSha256,
            String processingStatus,
            String idempotencyKey
    ) {}

    /**
     * The administrative view of a tenant's active allowance.
     *
     * <p>Distinct from {@link UsageSnapshot}, which is what the tenant sees.
     * This one exposes the allocation identifier and the optimistic-concurrency
     * version an operator needs in order to change the allowance, plus the two
     * floors below which a decrease must be refused.
     *
     * <p>{@code minimumTokenLimit} and {@code minimumCreditLimit} are
     * {@code consumed + reserved}. They are returned rather than left for the
     * caller to compute because a reservation is a promise already made to the
     * tenant: lowering a limit underneath outstanding reservations would either
     * be rejected by the database CHECK as an opaque constraint violation, or --
     * if the constraint were ever relaxed -- retroactively invalidate work the
     * tenant has already been told it may perform.
     */
    record QuotaAdministrationView(
            String organizationId,
            String quotaAllocationId,
            String subscriptionId,
            String planId,
            String planDisplayName,
            Instant periodStartsAt,
            Instant periodEndsAt,
            BigDecimal tokenLimit,
            BigDecimal creditLimit,
            BigDecimal consumedTokens,
            BigDecimal consumedCredits,
            BigDecimal reservedTokens,
            BigDecimal reservedCredits,
            BigDecimal minimumTokenLimit,
            BigDecimal minimumCreditLimit,
            long allocationVersion
    ) {}

    record ReconciliationCase(
            String reconciliationCaseId,
            String provider,
            String providerObjectRef,
            String expectedState,
            String observedState,
            String status,
            String reasonCode,
            Instant openedAt,
            Instant resolvedAt,
            String resolverActorId,
            String resolutionRef
    ) {}

    UsageSnapshot currentUsage(String organizationId, String actorId);

    List<UsageHistoryPoint> usageHistory(
            String organizationId,
            String actorId,
            Instant fromInclusive,
            Instant toExclusive,
            String bucket
    );

    UsageReservation reserve(
            String organizationId,
            String actorId,
            String subscriptionId,
            String reservationId,
            String idempotencyKey,
            String operationKey,
            BigDecimal requestedTokens,
            BigDecimal requestedCredits,
            Instant expiresAt
    );

    UsageSettlement settle(
            String organizationId,
            String actorId,
            String reservationId,
            String eventPrefix,
            BigDecimal actualTokens,
            BigDecimal actualCredits,
            String tokenClass,
            String provider,
            String providerReceiptRef,
            String providerCostCurrency,
            BigDecimal providerCostMinor,
            Instant occurredAt
    );

    void release(String organizationId, String actorId, String reservationId, String reasonCode);

    void correct(
            String organizationId,
            String actorId,
            String ledgerEntryId,
            String originalLedgerEntryId,
            BigDecimal quantity,
            String reasonCode,
            String idempotencyKey
    );

    TrialGrant grantTrial(
            String organizationId,
            String actorId,
            String verifiedSubjectHash,
            String idempotencyKey
    );

    AlertPreference alertPreference(String organizationId, String actorId);

    List<UsageAlert> usageAlerts(String organizationId, String actorId, Instant since);

    AlertPreference saveAlertPreference(
            String organizationId,
            String actorId,
            String scope,
            List<Integer> thresholdBps,
            boolean emailEnabled,
            boolean inAppEnabled,
            long expectedVersion
    );

    CheckoutRecord prepareCheckout(
            String organizationId,
            String actorId,
            String checkoutSessionId,
            String planId,
            Instant expiresAt,
            String idempotencyKey,
            String requestHash
    );

    CheckoutRecord completeCheckout(
            String organizationId,
            String actorId,
            String idempotencyKey,
            String providerSessionRef,
            String checkoutUrl,
            Instant expiresAt
    );

    void markCheckoutReconciliationRequired(
            String organizationId,
            String actorId,
            String idempotencyKey,
            String reasonCode
    );

    void markCheckoutFailed(
            String organizationId,
            String actorId,
            String idempotencyKey,
            String reasonCode
    );

    boolean applyProviderEvent(
            String organizationId,
            String actorId,
            ProviderEvent event,
            String planId,
            String localSubscriptionId,
            String quotaAllocationId,
            Instant periodStart,
            Instant periodEnd
    );

    List<ReconciliationCase> reconciliationCases(
            String organizationId,
            String actorId,
            String status,
            int limit
    );

    void resolveReconciliationCase(
            String organizationId,
            String actorId,
            String reconciliationCaseId,
            String resolutionStatus,
            String resolutionRef,
            String idempotencyKey
    );

    /** The active allowance of {@code organizationId}, for operator review. */
    QuotaAdministrationView quotaForAdministration(String organizationId);

    /**
     * Change a tenant's allowance.
     *
     * <p>{@code expectedVersion} must equal the allocation's current version;
     * a mismatch means another operator changed the allowance in between and
     * the caller's view of the before-state is stale, so the write is refused
     * rather than applied on top of an unseen change.
     *
     * <p>{@code reasonCode} is recorded on the append-only subscription event
     * log alongside both the previous and the new limits.
     */
    QuotaAdministrationView adjustQuota(
            String organizationId,
            String actorId,
            String quotaAllocationId,
            BigDecimal tokenLimit,
            BigDecimal creditLimit,
            long expectedVersion,
            String reasonCode
    );

    SubscriptionBinding currentSubscription(String organizationId, String actorId);

    void scheduleCancellation(String organizationId, String actorId, String subscriptionId);
}
