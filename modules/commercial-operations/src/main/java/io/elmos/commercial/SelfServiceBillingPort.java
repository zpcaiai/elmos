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

    SubscriptionBinding currentSubscription(String organizationId, String actorId);

    void scheduleCancellation(String organizationId, String actorId, String subscriptionId);
}
