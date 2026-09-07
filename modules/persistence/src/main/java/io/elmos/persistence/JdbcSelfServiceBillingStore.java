package io.elmos.persistence;

import static io.elmos.persistence.SqlTimestamps.offset;

import io.elmos.commercial.PricingPlanCatalog;
import io.elmos.commercial.SelfServiceBillingPort;
import io.elmos.commercial.SelfServiceBillingPort.BillingStateException;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.support.TransactionTemplate;

import java.math.BigDecimal;
import java.sql.Array;
import java.sql.SQLException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.UUID;
import java.util.function.Supplier;

/**
 * PostgreSQL 17 adapter for the exact self-service billing contract.
 *
 * <p>RLS context and each operation share one database transaction. Reservation,
 * settlement, correction, trial, and provider-event transitions delegate to the
 * row-locking functions owned by Flyway V49.</p>
 */
public final class JdbcSelfServiceBillingStore implements SelfServiceBillingPort {
    private static final String CATALOG_VERSION = PricingPlanCatalog.CATALOG_VERSION;
    private final JdbcClient jdbc;
    private final TransactionTemplate transactions;

    public JdbcSelfServiceBillingStore(JdbcClient jdbc, TransactionTemplate transactions) {
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
        this.transactions = Objects.requireNonNull(transactions, "transactions");
    }

    @Override
    public UsageSnapshot currentUsage(String organizationId, String actorId) {
        return inTenant(organizationId, () -> jdbc.sql("""
                select s.subscription_id, s.plan_id, q.period_start, q.period_end,
                       q.token_limit, q.credit_limit, q.consumed_tokens, q.consumed_credits,
                       q.reserved_tokens, q.reserved_credits,
                       count(e.usage_event_id) filter (where e.reconciliation_status = 'RECONCILED') reconciled_count,
                       count(e.usage_event_id) filter (where e.reconciliation_status = 'PENDING') pending_count,
                       max(e.recorded_at) event_watermark
                  from subscriptions s
                  join quota_allocations q on q.subscription_id = s.subscription_id
                  left join usage_events e on e.quota_allocation_id = q.quota_allocation_id
                 where s.organization_id = :organization
                   and s.status in ('ACTIVE', 'TRIALING', 'PAST_DUE')
                   and q.status = 'ACTIVE'
                   and q.period_start <= current_timestamp and q.period_end > current_timestamp
                 group by s.subscription_id, s.plan_id, q.period_start, q.period_end,
                          q.token_limit, q.credit_limit, q.consumed_tokens, q.consumed_credits,
                          q.reserved_tokens, q.reserved_credits
                 order by q.period_start desc
                 limit 1
                """).param("organization", organizationId)
                .query((rs, row) -> {
                    var plan = PricingPlanCatalog.requirePlan(rs.getString("plan_id"));
                    var tokenLimit = rs.getBigDecimal("token_limit");
                    var creditLimit = rs.getBigDecimal("credit_limit");
                    var consumedTokens = rs.getBigDecimal("consumed_tokens");
                    var consumedCredits = rs.getBigDecimal("consumed_credits");
                    var reservedTokens = rs.getBigDecimal("reserved_tokens");
                    var reservedCredits = rs.getBigDecimal("reserved_credits");
                    var end = instant(rs.getObject("period_end", OffsetDateTime.class));
                    var watermark = rs.getObject("event_watermark", OffsetDateTime.class);
                    return new UsageSnapshot(
                            "2.0.0",
                            rs.getLong("pending_count") == 0 ? "CURRENT" : "PARTIAL",
                            organizationId,
                            actorId,
                            rs.getString("subscription_id"),
                            plan.planId(),
                            plan.displayName(),
                            plan.allowance().window().name(),
                            instant(rs.getObject("period_start", OffsetDateTime.class)),
                            end,
                            plan.allowance().window() == PricingPlanCatalog.AllowanceWindow.MONTHLY ? end : null,
                            measure(consumedTokens, reservedTokens, tokenLimit),
                            measure(consumedCredits, reservedCredits, creditLimit),
                            rs.getLong("reconciled_count"),
                            rs.getLong("pending_count"),
                            watermark == null ? null : instant(watermark),
                            Instant.now(),
                            5
                    );
                }).optional().orElseThrow(() -> new BillingStateException(
                        "ACTIVE_ALLOWANCE_NOT_FOUND", "No current allowance is bound to this organization.")));
    }

    @Override
    public List<UsageHistoryPoint> usageHistory(
            String organizationId,
            String actorId,
            Instant fromInclusive,
            Instant toExclusive,
            String bucket
    ) {
        requireWindow(fromInclusive, toExclusive);
        String normalizedBucket = switch (Objects.requireNonNull(bucket, "bucket").toUpperCase(Locale.ROOT)) {
            case "HOUR" -> "hour";
            case "DAY" -> "day";
            default -> throw new IllegalArgumentException("bucket must be HOUR or DAY");
        };
        String sql = """
                select date_trunc('%s', l.occurred_at) bucket_start, l.meter_id,
                       l.operation_key, coalesce(e.token_class, '') token_class, l.actor_id,
                       coalesce(e.provider, '') provider,
                       coalesce(sum(l.quantity) filter (where l.direction = 'DEBIT'), 0) debited,
                       coalesce(sum(l.quantity) filter (where l.direction = 'CREDIT'), 0) credited
                  from usage_ledger_entries l
                  left join usage_events e on e.usage_event_id = l.usage_event_id
                 where l.organization_id = :organization
                   and l.meter_id is not null
                   and l.occurred_at >= :from and l.occurred_at < :to
                 group by bucket_start, l.meter_id, l.operation_key, coalesce(e.token_class, ''),
                          l.actor_id, coalesce(e.provider, '')
                 order by bucket_start, l.meter_id, token_class, l.actor_id
                """.formatted(normalizedBucket);
        return inTenant(organizationId, () -> jdbc.sql(sql)
                .param("organization", organizationId)
                .param("from", offset(fromInclusive))
                .param("to", offset(toExclusive))
                .query((rs, row) -> {
                    BigDecimal debit = rs.getBigDecimal("debited");
                    BigDecimal credit = rs.getBigDecimal("credited");
                    return new UsageHistoryPoint(
                            instant(rs.getObject("bucket_start", OffsetDateTime.class)),
                            rs.getString("meter_id"),
                            rs.getString("operation_key"),
                            nullable(rs.getString("token_class")),
                            rs.getString("actor_id"),
                            nullable(rs.getString("provider")),
                            debit,
                            credit,
                            debit.subtract(credit)
                    );
                }).list());
    }

    @Override
    public UsageReservation reserve(
            String organizationId,
            String actorId,
            String subscriptionId,
            String reservationId,
            String idempotencyKey,
            String operationKey,
            BigDecimal requestedTokens,
            BigDecimal requestedCredits,
            Instant expiresAt
    ) {
        return inTenant(organizationId, () -> jdbc.sql("""
                select * from elmos_reserve_usage(
                    :reservation, :subscription, :actor, :idempotency, :operation,
                    :tokens, :credits, :expires)
                """).param("reservation", reservationId)
                .param("subscription", subscriptionId)
                .param("actor", actorId)
                .param("idempotency", idempotencyKey)
                .param("operation", operationKey)
                .param("tokens", integerQuantity(requestedTokens, "requestedTokens"))
                .param("credits", integerQuantity(requestedCredits, "requestedCredits"))
                .param("expires", offset(expiresAt))
                .query((rs, row) -> new UsageReservation(
                        rs.getString("reservation_id"),
                        rs.getString("decision"),
                        rs.getBigDecimal("remaining_tokens"),
                        rs.getBigDecimal("remaining_credits")
                )).single());
    }

    @Override
    public UsageSettlement settle(
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
    ) {
        return inTenant(organizationId, () -> jdbc.sql("""
                select * from elmos_settle_usage(
                    :reservation, :eventPrefix, :tokens, :credits, :tokenClass,
                    :provider, :receipt, :costCurrency, :costMinor, :occurred)
                """).param("reservation", reservationId)
                .param("eventPrefix", eventPrefix)
                .param("tokens", integerQuantity(actualTokens, "actualTokens"))
                .param("credits", integerQuantity(actualCredits, "actualCredits"))
                .param("tokenClass", tokenClass)
                .param("provider", provider)
                .param("receipt", providerReceiptRef)
                .param("costCurrency", providerCostCurrency)
                .param("costMinor", providerCostMinor)
                .param("occurred", offset(occurredAt))
                .query((rs, row) -> new UsageSettlement(
                        rs.getString("reservation_id"),
                        rs.getString("status"),
                        rs.getBigDecimal("consumed_tokens"),
                        rs.getBigDecimal("consumed_credits"),
                        rs.getBigDecimal("remaining_tokens"),
                        rs.getBigDecimal("remaining_credits")
                )).single());
    }

    @Override
    public void release(String organizationId, String actorId, String reservationId, String reasonCode) {
        inTenant(organizationId, () -> {
            jdbc.sql("select elmos_release_usage(:reservation, :reason)")
                    .param("reservation", reservationId).param("reason", reasonCode).query().singleRow();
            return null;
        });
    }

    @Override
    public void correct(
            String organizationId,
            String actorId,
            String ledgerEntryId,
            String originalLedgerEntryId,
            BigDecimal quantity,
            String reasonCode,
            String idempotencyKey
    ) {
        inTenant(organizationId, () -> {
            jdbc.sql("select elmos_correct_usage(:entry, :original, :actor, :quantity, :reason, :idempotency)")
                    .param("entry", ledgerEntryId)
                    .param("original", originalLedgerEntryId)
                    .param("actor", actorId)
                    .param("quantity", integerQuantity(quantity, "quantity"))
                    .param("reason", reasonCode)
                    .param("idempotency", idempotencyKey)
                    .query().singleRow();
            return null;
        });
    }

    @Override
    public TrialGrant grantTrial(
            String organizationId,
            String actorId,
            String verifiedSubjectHash,
            String idempotencyKey
    ) {
        String suffix = UUID.randomUUID().toString();
        String grantId = "trial-" + suffix;
        String subscriptionId = "sub-trial-" + suffix;
        String allocationId = "quota-trial-" + suffix;
        return inTenant(organizationId, () -> {
            jdbc.sql("select elmos_grant_trial(:grant, :subscription, :allocation, :actor, :subjectHash, :idempotency)")
                    .param("grant", grantId)
                    .param("subscription", subscriptionId)
                    .param("allocation", allocationId)
                    .param("actor", actorId)
                    .param("subjectHash", verifiedSubjectHash)
                    .param("idempotency", idempotencyKey)
                    .query().singleRow();
            return jdbc.sql("""
                    select trial_grant_id, subscription_id, plan_id, starts_at, ends_at, status
                      from trial_grants
                     where organization_id = :organization and idempotency_key = :idempotency
                    """).param("organization", organizationId).param("idempotency", idempotencyKey)
                    .query((rs, row) -> new TrialGrant(
                            rs.getString("trial_grant_id"),
                            rs.getString("subscription_id"),
                            rs.getString("plan_id"),
                            instant(rs.getObject("starts_at", OffsetDateTime.class)),
                            instant(rs.getObject("ends_at", OffsetDateTime.class)),
                            rs.getString("status")
                    )).single();
        });
    }

    @Override
    public AlertPreference alertPreference(String organizationId, String actorId) {
        return inTenant(organizationId, () -> jdbc.sql("""
                select usage_alert_preference_id, actor_id, scope, threshold_bps,
                       email_enabled, in_app_enabled, version
                  from usage_alert_preferences
                 where organization_id = :organization and actor_id = :actor
                """).param("organization", organizationId).param("actor", actorId)
                .query((rs, row) -> alertPreference(rs)).optional()
                .orElse(new AlertPreference(
                        "default", actorId, "ACTOR",
                        List.of(5000, 8000, 9500, 10000), false, true, 0)));
    }

    @Override
    public List<UsageAlert> usageAlerts(String organizationId, String actorId, Instant since) {
        if (since == null || since.isBefore(Instant.now().minusSeconds(366L * 24 * 60 * 60))) {
            throw new IllegalArgumentException("usage alert window is invalid");
        }
        return inTenant(organizationId, () -> jdbc.sql("""
                select usage_alert_delivery_id, meter_id, threshold_bps,
                       channel, status, occurred_at
                  from usage_alert_deliveries
                 where organization_id = :organization and actor_id = :actor
                   and occurred_at >= :since
                 order by occurred_at desc
                 limit 100
                """).param("organization", organizationId).param("actor", actorId)
                .param("since", offset(since))
                .query((rs, row) -> new UsageAlert(
                        rs.getString("usage_alert_delivery_id"),
                        rs.getString("meter_id"),
                        rs.getInt("threshold_bps"),
                        rs.getString("channel"),
                        rs.getString("status"),
                        instant(rs.getObject("occurred_at", OffsetDateTime.class))
                )).list());
    }

    @Override
    public AlertPreference saveAlertPreference(
            String organizationId,
            String actorId,
            String scope,
            List<Integer> thresholdBps,
            boolean emailEnabled,
            boolean inAppEnabled,
            long expectedVersion
    ) {
        validateThresholds(thresholdBps);
        if (!"ACTOR".equals(scope) && !"ORGANIZATION".equals(scope)) {
            throw new IllegalArgumentException("alert scope is invalid");
        }
        return inTenant(organizationId, () -> {
            String preferenceId = "usage-alert-" + UUID.randomUUID();
            int changed;
            if (expectedVersion == 0) {
                changed = jdbc.sql("""
                        insert into usage_alert_preferences(
                            usage_alert_preference_id, organization_id, actor_id, scope,
                            threshold_bps, email_enabled, in_app_enabled, version)
                        values (:id, :organization, :actor, :scope, :thresholds,
                                :email, :inApp, 1)
                        on conflict (organization_id, actor_id) do nothing
                        """).param("id", preferenceId)
                        .param("organization", organizationId).param("actor", actorId)
                        .param("scope", scope).param("thresholds", thresholdBps.toArray(Integer[]::new))
                        .param("email", emailEnabled).param("inApp", inAppEnabled).update();
            } else {
                changed = jdbc.sql("""
                        update usage_alert_preferences
                           set scope = :scope, threshold_bps = :thresholds,
                               email_enabled = :email, in_app_enabled = :inApp,
                               version = version + 1, updated_at = current_timestamp
                         where organization_id = :organization and actor_id = :actor
                           and version = :expected
                        """).param("scope", scope).param("thresholds", thresholdBps.toArray(Integer[]::new))
                        .param("email", emailEnabled).param("inApp", inAppEnabled)
                        .param("organization", organizationId).param("actor", actorId)
                        .param("expected", expectedVersion).update();
            }
            if (changed != 1) {
                throw new BillingStateException("ALERT_PREFERENCE_VERSION_CONFLICT",
                        "Alert preferences changed concurrently.");
            }
            return alertPreference(organizationId, actorId);
        });
    }

    @Override
    public CheckoutRecord prepareCheckout(
            String organizationId,
            String actorId,
            String checkoutSessionId,
            String planId,
            Instant expiresAt,
            String idempotencyKey,
            String requestHash
    ) {
        var plan = PricingPlanCatalog.requirePlan(planId);
        if (plan.billingPeriod() == PricingPlanCatalog.BillingPeriod.TRIAL) {
            throw new IllegalArgumentException("trial cannot be purchased");
        }
        BigDecimal amountMinor = plan.price().amount().movePointRight(2);
        return inTenant(organizationId, () -> {
            String existingHash = jdbc.sql("""
                    select request_hash from payment_checkout_sessions
                     where organization_id = :organization and idempotency_key = :idempotency
                    """).param("organization", organizationId).param("idempotency", idempotencyKey)
                    .query(String.class).optional().orElse(null);
            if (existingHash != null && !existingHash.equals(requestHash)) {
                throw new BillingStateException(
                        "CHECKOUT_IDEMPOTENCY_CONFLICT",
                        "Checkout idempotency key was reused for a different request.");
            }
            jdbc.sql("""
                    insert into payment_checkout_sessions(
                        checkout_session_id, organization_id, actor_id, plan_id,
                        catalog_version, currency, amount_minor, provider,
                        status, expires_at,
                        idempotency_key, request_hash)
                    values (:id, :organization, :actor, :plan, :catalog, 'CNY',
                            :amount, 'STRIPE_CHECKOUT', 'CREATING',
                            :expires, :idempotency, :requestHash)
                    on conflict (organization_id, idempotency_key) do nothing
                    """).param("id", checkoutSessionId).param("organization", organizationId)
                    .param("actor", actorId).param("plan", planId).param("catalog", CATALOG_VERSION)
                    .param("amount", amountMinor).param("expires", offset(expiresAt))
                    .param("idempotency", idempotencyKey).param("requestHash", requestHash).update();
            return jdbc.sql("""
                    select checkout_session_id, plan_id, catalog_version, currency,
                           amount_minor, provider_session_ref, checkout_url, status, expires_at
                      from payment_checkout_sessions
                     where organization_id = :organization and idempotency_key = :idempotency
                    """).param("organization", organizationId).param("idempotency", idempotencyKey)
                    .query((rs, row) -> new CheckoutRecord(
                            rs.getString("checkout_session_id"), rs.getString("plan_id"),
                            rs.getString("catalog_version"), rs.getString("currency").trim(),
                            rs.getBigDecimal("amount_minor"), rs.getString("provider_session_ref"),
                            rs.getString("checkout_url"), rs.getString("status"),
                            instant(rs.getObject("expires_at", OffsetDateTime.class))
                    )).single();
        });
    }

    @Override
    public CheckoutRecord completeCheckout(
            String organizationId,
            String actorId,
            String idempotencyKey,
            String providerSessionRef,
            String checkoutUrl,
            Instant expiresAt
    ) {
        return inTenant(organizationId, () -> {
            int changed = jdbc.sql("""
                    update payment_checkout_sessions
                       set provider_session_ref = :providerSession, checkout_url = :url,
                           expires_at = :expires, status = 'OPEN',
                           updated_at = current_timestamp
                     where organization_id = :organization and actor_id = :actor
                       and idempotency_key = :idempotency
                       and (
                           status in ('CREATING', 'RECONCILIATION_REQUIRED')
                           or (status = 'OPEN' and provider_session_ref = :providerSession)
                       )
                    """).param("providerSession", providerSessionRef).param("url", checkoutUrl)
                    .param("expires", offset(expiresAt)).param("organization", organizationId)
                    .param("actor", actorId).param("idempotency", idempotencyKey).update();
            if (changed != 1) {
                throw new BillingStateException(
                        "CHECKOUT_STATE_CONFLICT", "Checkout could not be completed safely.");
            }
            return checkout(organizationId, idempotencyKey);
        });
    }

    @Override
    public void markCheckoutReconciliationRequired(
            String organizationId,
            String actorId,
            String idempotencyKey,
            String reasonCode
    ) {
        inTenant(organizationId, () -> {
            jdbc.sql("""
                    update payment_checkout_sessions
                       set status = 'RECONCILIATION_REQUIRED', updated_at = current_timestamp
                     where organization_id = :organization and actor_id = :actor
                       and idempotency_key = :idempotency and status = 'CREATING'
                    """).param("organization", organizationId).param("actor", actorId)
                    .param("idempotency", idempotencyKey).update();
            jdbc.sql("""
                    insert into payment_reconciliation_cases(
                        payment_reconciliation_case_id, organization_id, provider,
                        provider_object_ref, expected_state, observed_state, status,
                        reason_code, idempotency_key)
                    values (:caseId, :organization, 'STRIPE_CHECKOUT', :object,
                            'OPEN_CHECKOUT_SESSION', 'PROVIDER_RESULT_UNKNOWN', 'OPEN',
                            :reason, :reconciliationKey)
                    on conflict (organization_id, idempotency_key) do nothing
                    """).param("caseId", "recon-" + UUID.randomUUID())
                    .param("organization", organizationId).param("object", idempotencyKey)
                    .param("reason", reasonCode)
                    .param("reconciliationKey", idempotencyKey + ":checkout-recon").update();
            return null;
        });
    }

    @Override
    public void markCheckoutFailed(
            String organizationId,
            String actorId,
            String idempotencyKey,
            String reasonCode
    ) {
        inTenant(organizationId, () -> {
            int changed = jdbc.sql("""
                    update payment_checkout_sessions
                       set status = 'FAILED',
                           updated_at = current_timestamp,
                           failure_code = :reason
                     where organization_id = :organization and actor_id = :actor
                       and idempotency_key = :idempotency and status = 'CREATING'
                    """).param("reason", reasonCode)
                    .param("organization", organizationId).param("actor", actorId)
                    .param("idempotency", idempotencyKey).update();
            if (changed != 1) {
                throw new BillingStateException(
                        "CHECKOUT_STATE_CONFLICT", "Checkout could not be marked failed safely.");
            }
            return null;
        });
    }

    @Override
    public boolean applyProviderEvent(
            String organizationId,
            String actorId,
            ProviderEvent event,
            String planId,
            String localSubscriptionId,
            String quotaAllocationId,
            Instant periodStart,
            Instant periodEnd
    ) {
        Objects.requireNonNull(event, "event");
        return inTenant(organizationId, () -> {
            boolean exists = jdbc.sql("""
                    select count(*) from payment_provider_events
                     where provider = 'STRIPE_CHECKOUT' and payment_provider_event_id = :event
                    """).param("event", event.eventId()).query(Long.class).single() > 0;
            if (exists) return false;

            String processingStatus = event.processingStatus();
            if (!"APPLIED".equals(processingStatus)) {
                insertProviderEvent(organizationId, event, "RECONCILIATION_REQUIRED");
                openReconciliationCase(organizationId, event);
                return true;
            }
            switch (event.eventType()) {
                case "checkout.session.completed" -> {
                    int changed = jdbc.sql("""
                            update payment_checkout_sessions
                               set status = 'COMPLETED', provider_customer_ref = :customer,
                                   completed_at = :completed, updated_at = current_timestamp
                             where organization_id = :organization
                               and provider_session_ref = :session and plan_id = :plan
                               and status in ('OPEN', 'COMPLETED')
                            """).param("customer", event.customerRef())
                            .param("completed", offset(event.eventCreatedAt()))
                            .param("organization", organizationId).param("session", event.objectRef())
                            .param("plan", planId).update();
                    if (changed != 1) processingStatus = "RECONCILIATION_REQUIRED";
                }
                case "invoice.paid" -> {
                    if (requiredProviderFields(event, planId, localSubscriptionId, quotaAllocationId,
                            periodStart, periodEnd)) {
                        jdbc.sql("""
                                select elmos_activate_subscription_period(
                                    :localSubscription, :allocation, :actor, :plan,
                                    'STRIPE_CHECKOUT', :customer, :providerSubscription,
                                    :periodStart, :periodEnd, :event, :idempotency)
                                """).param("localSubscription", localSubscriptionId)
                                .param("allocation", quotaAllocationId).param("actor", actorId)
                                .param("plan", planId).param("customer", event.customerRef())
                                .param("providerSubscription", event.subscriptionRef())
                                .param("periodStart", offset(periodStart)).param("periodEnd", offset(periodEnd))
                                .param("event", event.eventId()).param("idempotency", event.idempotencyKey())
                                .query().singleRow();
                    } else {
                        processingStatus = "RECONCILIATION_REQUIRED";
                    }
                }
                case "invoice.payment_failed" -> {
                    int changed = updateSubscriptionState(
                            organizationId, event.subscriptionRef(), "PAST_DUE", false);
                    if (changed != 1) processingStatus = "RECONCILIATION_REQUIRED";
                }
                case "customer.subscription.deleted" -> {
                    int changed = updateSubscriptionState(
                            organizationId, event.subscriptionRef(), "CANCELLED", false);
                    if (changed != 1) processingStatus = "RECONCILIATION_REQUIRED";
                }
                default -> processingStatus = "RECONCILIATION_REQUIRED";
            }
            insertProviderEvent(organizationId, event, processingStatus);
            if ("RECONCILIATION_REQUIRED".equals(processingStatus)) {
                openReconciliationCase(organizationId, event);
            }
            return true;
        });
    }

    @Override
    public List<ReconciliationCase> reconciliationCases(
            String organizationId,
            String actorId,
            String status,
            int limit
    ) {
        String normalizedStatus = Objects.requireNonNull(status, "status").toUpperCase(Locale.ROOT);
        if (!List.of("OPEN", "RESOLVED", "REJECTED").contains(normalizedStatus)) {
            throw new IllegalArgumentException("reconciliation status is invalid");
        }
        if (limit < 1 || limit > 200) {
            throw new IllegalArgumentException("reconciliation limit is invalid");
        }
        return inTenant(organizationId, () -> jdbc.sql("""
                select payment_reconciliation_case_id, provider, provider_object_ref,
                       expected_state, observed_state, status, reason_code, opened_at,
                       resolved_at, resolver_actor_id, resolution_ref
                  from payment_reconciliation_cases
                 where organization_id = :organization and status = :status
                 order by opened_at
                 limit :limit
                """).param("organization", organizationId).param("status", normalizedStatus)
                .param("limit", limit)
                .query((rs, row) -> new ReconciliationCase(
                        rs.getString("payment_reconciliation_case_id"),
                        rs.getString("provider"),
                        rs.getString("provider_object_ref"),
                        rs.getString("expected_state"),
                        rs.getString("observed_state"),
                        rs.getString("status"),
                        rs.getString("reason_code"),
                        instant(rs.getObject("opened_at", OffsetDateTime.class)),
                        nullableInstant(rs.getObject("resolved_at", OffsetDateTime.class)),
                        rs.getString("resolver_actor_id"),
                        rs.getString("resolution_ref")
                )).list());
    }

    @Override
    public void resolveReconciliationCase(
            String organizationId,
            String actorId,
            String reconciliationCaseId,
            String resolutionStatus,
            String resolutionRef,
            String idempotencyKey
    ) {
        inTenant(organizationId, () -> {
            jdbc.sql("""
                    select elmos_resolve_payment_reconciliation(
                        :caseId, :actor, :status, :reference, :idempotency)
                    """).param("caseId", reconciliationCaseId)
                    .param("actor", actorId)
                    .param("status", resolutionStatus)
                    .param("reference", resolutionRef)
                    .param("idempotency", idempotencyKey)
                    .query().singleRow();
            return null;
        });
    }

    @Override
    public SubscriptionBinding currentSubscription(String organizationId, String actorId) {
        return inTenant(organizationId, () -> jdbc.sql("""
                select subscription_id, plan_id, status, provider,
                       provider_subscription_ref, current_period_end, cancel_at_period_end
                  from subscriptions
                 where organization_id = :organization
                   and plan_id is not null
                   and status in ('ACTIVE', 'TRIALING', 'PAST_DUE')
                 order by current_period_end desc
                 limit 1
                """).param("organization", organizationId)
                .query((rs, row) -> new SubscriptionBinding(
                        rs.getString("subscription_id"),
                        rs.getString("plan_id"),
                        rs.getString("status"),
                        rs.getString("provider"),
                        rs.getString("provider_subscription_ref"),
                        instant(rs.getObject("current_period_end", OffsetDateTime.class)),
                        rs.getBoolean("cancel_at_period_end")
                )).optional().orElseThrow(() -> new BillingStateException(
                        "ACTIVE_SUBSCRIPTION_NOT_FOUND", "No active subscription was found.")));
    }

    /**
     * The largest allowance an operator may set: 1e27, or 28 digits.
     *
     * <p>{@code token_limit} and {@code credit_limit} are {@code numeric(30,0)},
     * so anything at or above 1e30 fails at the column. Stopping three orders of
     * magnitude short means an out-of-range request is refused by name instead
     * of surfacing as a numeric overflow from the driver, and leaves headroom
     * for the {@code consumed + reserved} sums to stay inside the type even
     * after a tenant has run against the ceiling for a full period.
     */
    private static final BigDecimal MAXIMUM_LIMIT = new BigDecimal("1000000000000000000000000000");

    /**
     * An operator reason is a code, not prose.
     *
     * <p>These values land in the append-only event log and flow out through the
     * audit export, so free text would put operator-authored strings into a CSV
     * that other systems parse. A constrained token keeps the log groupable and
     * the export inert.
     */
    private static final java.util.regex.Pattern REASON_CODE =
            java.util.regex.Pattern.compile("^[A-Z][A-Z0-9_]{2,63}$");

    @Override
    public QuotaAdministrationView quotaForAdministration(String organizationId) {
        return inTenant(organizationId, () -> readQuota(organizationId));
    }

    @Override
    public QuotaAdministrationView adjustQuota(
            String organizationId,
            String actorId,
            String quotaAllocationId,
            BigDecimal tokenLimit,
            BigDecimal creditLimit,
            long expectedVersion,
            String reasonCode
    ) {
        // Every check that does not need the database runs first, so a malformed
        // request never opens a transaction and never binds a tenant.
        requireIdentifier(organizationId, "organizationId");
        requireIdentifier(actorId, "actorId");
        requireIdentifier(quotaAllocationId, "quotaAllocationId");
        requireLimit(tokenLimit, "tokenLimit");
        requireLimit(creditLimit, "creditLimit");
        if (expectedVersion < 0) {
            throw new IllegalArgumentException("expectedVersion must not be negative");
        }
        if (reasonCode == null || !REASON_CODE.matcher(reasonCode).matches()) {
            throw new IllegalArgumentException(
                    "reasonCode must match " + REASON_CODE.pattern());
        }

        return inTenant(organizationId, () -> {
            QuotaAdministrationView current = readQuota(organizationId);
            if (!current.quotaAllocationId().equals(quotaAllocationId)) {
                // The operator is holding a view of an allocation that is no
                // longer the active one -- most often because the billing period
                // rolled over between reading and submitting.
                throw new BillingStateException("QUOTA_ALLOCATION_NOT_ACTIVE",
                        "The allocation being adjusted is not the organization's active allowance.");
            }
            if (current.allocationVersion() != expectedVersion) {
                throw new BillingStateException("QUOTA_ALLOCATION_VERSION_CONFLICT",
                        "The allowance changed since it was read; re-read it before adjusting.");
            }
            if (tokenLimit.compareTo(current.minimumTokenLimit()) < 0) {
                throw new BillingStateException("QUOTA_BELOW_OUTSTANDING_TOKENS",
                        "tokenLimit " + tokenLimit.toPlainString() + " is below the "
                                + current.minimumTokenLimit().toPlainString()
                                + " tokens already consumed or reserved.");
            }
            if (creditLimit.compareTo(current.minimumCreditLimit()) < 0) {
                throw new BillingStateException("QUOTA_BELOW_OUTSTANDING_CREDITS",
                        "creditLimit " + creditLimit.toPlainString() + " is below the "
                                + current.minimumCreditLimit().toPlainString()
                                + " credits already consumed or reserved.");
            }
            if (tokenLimit.compareTo(current.tokenLimit()) == 0
                    && creditLimit.compareTo(current.creditLimit()) == 0) {
                // A no-op write would still bump the version and append an audit
                // event that records no change, which corrupts the log's meaning.
                throw new BillingStateException("QUOTA_ADJUSTMENT_IS_A_NO_OP",
                        "The requested limits are identical to the current allowance.");
            }

            int changed = jdbc.sql("""
                    update quota_allocations
                       set token_limit = :tokenLimit, credit_limit = :creditLimit,
                           allocation_version = allocation_version + 1,
                           updated_at = current_timestamp
                     where organization_id = :organization
                       and quota_allocation_id = :allocation
                       and allocation_version = :expectedVersion
                    """).param("organization", organizationId)
                    .param("allocation", quotaAllocationId)
                    .param("tokenLimit", tokenLimit)
                    .param("creditLimit", creditLimit)
                    .param("expectedVersion", expectedVersion)
                    .update();
            if (changed != 1) {
                // The version was re-read inside this transaction, so losing the
                // race here means a concurrent writer committed between the read
                // and the update. Refusing is correct; retrying silently is not.
                throw new BillingStateException("QUOTA_ALLOCATION_VERSION_CONFLICT",
                        "The allowance changed while the adjustment was being applied.");
            }

            jdbc.sql("""
                    insert into subscription_events(
                        subscription_event_id, organization_id, schema_version, status,
                        idempotency_key, payload, subscription_id, actor_id, event_type,
                        effective_at, event_version)
                    values (:event, :organization, '2.0', 'APPLIED', :event,
                            jsonb_build_object(
                                'quotaAllocationId', :allocation::text,
                                'reasonCode', :reason::text,
                                'previousTokenLimit', :previousTokenLimit::text,
                                'previousCreditLimit', :previousCreditLimit::text,
                                'tokenLimit', :tokenLimit::text,
                                'creditLimit', :creditLimit::text),
                            :subscription, :actor, 'QUOTA_ADJUSTED', current_timestamp,
                            :eventVersion)
                    """).param("event", "quota-adjust-" + UUID.randomUUID())
                    .param("organization", organizationId)
                    .param("allocation", quotaAllocationId)
                    .param("reason", reasonCode)
                    .param("previousTokenLimit", current.tokenLimit().toPlainString())
                    .param("previousCreditLimit", current.creditLimit().toPlainString())
                    .param("tokenLimit", tokenLimit.toPlainString())
                    .param("creditLimit", creditLimit.toPlainString())
                    .param("subscription", current.subscriptionId())
                    .param("actor", actorId)
                    .param("eventVersion", expectedVersion + 1)
                    .update();

            return readQuota(organizationId);
        });
    }

    /** Caller must already be inside {@link #inTenant}. */
    private QuotaAdministrationView readQuota(String organizationId) {
        return jdbc.sql("""
                select q.quota_allocation_id, q.subscription_id, q.plan_id,
                       q.period_start, q.period_end,
                       q.token_limit, q.credit_limit,
                       q.consumed_tokens, q.consumed_credits,
                       q.reserved_tokens, q.reserved_credits,
                       q.allocation_version
                  from quota_allocations q
                  join subscriptions s on s.subscription_id = q.subscription_id
                 where q.organization_id = :organization
                   and q.status = 'ACTIVE'
                   and s.status in ('ACTIVE', 'TRIALING', 'PAST_DUE')
                   and q.period_start <= current_timestamp and q.period_end > current_timestamp
                 order by q.period_start desc
                 limit 1
                """).param("organization", organizationId)
                .query((rs, row) -> {
                    var plan = PricingPlanCatalog.requirePlan(rs.getString("plan_id"));
                    BigDecimal consumedTokens = rs.getBigDecimal("consumed_tokens");
                    BigDecimal consumedCredits = rs.getBigDecimal("consumed_credits");
                    BigDecimal reservedTokens = rs.getBigDecimal("reserved_tokens");
                    BigDecimal reservedCredits = rs.getBigDecimal("reserved_credits");
                    return new QuotaAdministrationView(
                            organizationId,
                            rs.getString("quota_allocation_id"),
                            rs.getString("subscription_id"),
                            plan.planId(),
                            plan.displayName(),
                            instant(rs.getObject("period_start", OffsetDateTime.class)),
                            instant(rs.getObject("period_end", OffsetDateTime.class)),
                            rs.getBigDecimal("token_limit"),
                            rs.getBigDecimal("credit_limit"),
                            consumedTokens, consumedCredits,
                            reservedTokens, reservedCredits,
                            consumedTokens.add(reservedTokens),
                            consumedCredits.add(reservedCredits),
                            rs.getLong("allocation_version"));
                }).optional().orElseThrow(() -> new BillingStateException(
                        "ACTIVE_ALLOWANCE_NOT_FOUND", "No current allowance is bound to this organization."));
    }

    private static void requireLimit(BigDecimal value, String field) {
        if (value == null) {
            throw new IllegalArgumentException(field + " is required");
        }
        if (value.signum() < 0) {
            throw new IllegalArgumentException(field + " must not be negative");
        }
        if (value.stripTrailingZeros().scale() > 0) {
            // numeric(30,0) would round a fractional limit silently.
            throw new IllegalArgumentException(field + " must be a whole number");
        }
        if (value.compareTo(MAXIMUM_LIMIT) > 0) {
            throw new IllegalArgumentException(
                    field + " must not exceed " + MAXIMUM_LIMIT.toPlainString());
        }
    }

    @Override
    public void scheduleCancellation(String organizationId, String actorId, String subscriptionId) {
        inTenant(organizationId, () -> {
            int changed = jdbc.sql("""
                    update subscriptions
                       set cancel_at_period_end = true, state_version = state_version + 1,
                           updated_at = current_timestamp
                     where organization_id = :organization and subscription_id = :subscription
                       and status in ('ACTIVE', 'TRIALING', 'PAST_DUE')
                    """).param("organization", organizationId).param("subscription", subscriptionId).update();
            if (changed != 1) {
                throw new BillingStateException("SUBSCRIPTION_NOT_CANCELLABLE",
                        "Subscription cannot be scheduled for cancellation.");
            }
            jdbc.sql("""
                    insert into subscription_events(
                        subscription_event_id, organization_id, schema_version, status,
                        idempotency_key, payload, subscription_id, actor_id, event_type,
                        effective_at, event_version)
                    values (:event, :organization, '2.0', 'APPLIED', :event, '{}'::jsonb,
                            :subscription, :actor, 'CANCEL_SCHEDULED', current_timestamp, 1)
                    """).param("event", "cancel-" + UUID.randomUUID())
                    .param("organization", organizationId).param("subscription", subscriptionId)
                    .param("actor", actorId).update();
            return null;
        });
    }

    private void insertProviderEvent(String organizationId, ProviderEvent event, String status) {
        jdbc.sql("""
                insert into payment_provider_events(
                    payment_provider_event_id, organization_id, provider, event_type,
                    object_ref, subscription_ref, customer_ref, invoice_ref,
                    amount_minor, currency, event_created_at, payload_sha256,
                    signature_verified, processing_status, idempotency_key)
                values (:event, :organization, 'STRIPE_CHECKOUT', :type, :object,
                        :subscription, :customer, :invoice, :amount, :currency,
                        :created, :digest, true, :status, :idempotency)
                """).param("event", event.eventId()).param("organization", organizationId)
                .param("type", event.eventType()).param("object", event.objectRef())
                .param("subscription", event.subscriptionRef()).param("customer", event.customerRef())
                .param("invoice", event.invoiceRef()).param("amount", event.amountMinor())
                .param("currency", event.currency()).param("created", offset(event.eventCreatedAt()))
                .param("digest", event.payloadSha256()).param("status", status)
                .param("idempotency", event.idempotencyKey()).update();
    }

    private CheckoutRecord checkout(String organizationId, String idempotencyKey) {
        return jdbc.sql("""
                select checkout_session_id, plan_id, catalog_version, currency,
                       amount_minor, provider_session_ref, checkout_url, status, expires_at
                  from payment_checkout_sessions
                 where organization_id = :organization and idempotency_key = :idempotency
                """).param("organization", organizationId).param("idempotency", idempotencyKey)
                .query((rs, row) -> new CheckoutRecord(
                        rs.getString("checkout_session_id"), rs.getString("plan_id"),
                        rs.getString("catalog_version"), rs.getString("currency").trim(),
                        rs.getBigDecimal("amount_minor"), rs.getString("provider_session_ref"),
                        rs.getString("checkout_url"), rs.getString("status"),
                        instant(rs.getObject("expires_at", OffsetDateTime.class))
                )).single();
    }

    private void openReconciliationCase(String organizationId, ProviderEvent event) {
        jdbc.sql("""
                insert into payment_reconciliation_cases(
                    payment_reconciliation_case_id, organization_id, provider,
                    provider_object_ref, expected_state, observed_state, status,
                    reason_code, idempotency_key)
                values (:caseId, :organization, 'STRIPE_CHECKOUT', :object,
                        'NORMALIZED_APPLIED_EVENT', :observed, 'OPEN',
                        'PROVIDER_EVENT_REQUIRES_RECONCILIATION', :idempotency)
                on conflict (organization_id, idempotency_key) do nothing
                """).param("caseId", "recon-" + UUID.randomUUID())
                .param("organization", organizationId).param("object", event.objectRef())
                .param("observed", event.eventType()).param("idempotency", event.idempotencyKey() + ":recon")
                .update();
    }

    private int updateSubscriptionState(
            String organizationId, String providerSubscriptionRef, String status, boolean cancelAtPeriodEnd
    ) {
        if (providerSubscriptionRef == null || providerSubscriptionRef.isBlank()) return 0;
        return jdbc.sql("""
                update subscriptions
                   set status = :status, cancel_at_period_end = :cancelAtPeriodEnd,
                       state_version = state_version + 1, updated_at = current_timestamp
                 where organization_id = :organization
                   and provider = 'STRIPE_CHECKOUT'
                   and provider_subscription_ref = :providerSubscription
                """).param("status", status).param("cancelAtPeriodEnd", cancelAtPeriodEnd)
                .param("organization", organizationId)
                .param("providerSubscription", providerSubscriptionRef).update();
    }

    private static boolean requiredProviderFields(
            ProviderEvent event,
            String planId,
            String localSubscriptionId,
            String quotaAllocationId,
            Instant periodStart,
            Instant periodEnd
    ) {
        return notBlank(planId) && notBlank(localSubscriptionId) && notBlank(quotaAllocationId)
                && notBlank(event.subscriptionRef()) && notBlank(event.customerRef())
                && periodStart != null && periodEnd != null && periodEnd.isAfter(periodStart);
    }

    private <T> T inTenant(String organizationId, Supplier<T> work) {
        requireIdentifier(organizationId, "organizationId");
        transactions.executeWithoutResult(status -> {
            bindTenant(organizationId);
            jdbc.sql("select elmos_expire_current_trial()").query(Boolean.class).single();
        });
        return transactions.execute(status -> {
            bindTenant(organizationId);
            return work.get();
        });
    }

    private void bindTenant(String organizationId) {
        jdbc.sql("select set_config('app.organization_id', :organization, true)")
                .param("organization", organizationId).query(String.class).single();
    }

    private static QuotaMeasure measure(BigDecimal consumed, BigDecimal reserved, BigDecimal limit) {
        BigDecimal remaining = limit.subtract(consumed).subtract(reserved).max(BigDecimal.ZERO);
        int bps = limit.signum() == 0 ? 10_000
                : consumed.add(reserved).multiply(BigDecimal.valueOf(10_000))
                .divideToIntegralValue(limit).min(BigDecimal.valueOf(10_000)).intValueExact();
        return new QuotaMeasure(consumed, reserved, limit, remaining, bps, remaining.signum() == 0);
    }

    private static AlertPreference alertPreference(java.sql.ResultSet rs) throws SQLException {
        Array values = rs.getArray("threshold_bps");
        Integer[] thresholds = (Integer[]) values.getArray();
        return new AlertPreference(
                rs.getString("usage_alert_preference_id"),
                rs.getString("actor_id"),
                rs.getString("scope"),
                Arrays.asList(thresholds),
                rs.getBoolean("email_enabled"),
                rs.getBoolean("in_app_enabled"),
                rs.getLong("version")
        );
    }

    private static BigDecimal integerQuantity(BigDecimal value, String field) {
        if (value == null || value.signum() < 0 || value.stripTrailingZeros().scale() > 0) {
            throw new IllegalArgumentException(field + " must be a non-negative integer");
        }
        return value;
    }

    private static void validateThresholds(List<Integer> thresholds) {
        List<Integer> allowed = List.of(1000, 2500, 5000, 7500, 8000, 9000, 9500, 10000);
        if (thresholds == null || thresholds.isEmpty() || thresholds.size() > 8
                || thresholds.stream().distinct().count() != thresholds.size()
                || !allowed.containsAll(thresholds)) {
            throw new IllegalArgumentException("usage alert thresholds are invalid");
        }
    }

    private static void requireWindow(Instant from, Instant to) {
        if (from == null || to == null || !to.isAfter(from)
                || to.isAfter(from.plusSeconds(366L * 24 * 60 * 60))) {
            throw new IllegalArgumentException("usage history window is invalid");
        }
    }

    private static void requireIdentifier(String value, String field) {
        if (value == null || !value.matches("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")) {
            throw new IllegalArgumentException(field + " is invalid");
        }
    }

    private static Instant instant(OffsetDateTime value) {
        return value.withOffsetSameInstant(ZoneOffset.UTC).toInstant();
    }

    private static Instant nullableInstant(OffsetDateTime value) {
        return value == null ? null : instant(value);
    }


    private static String nullable(String value) {
        return value == null || value.isBlank() ? null : value;
    }

    private static boolean notBlank(String value) {
        return value != null && !value.isBlank();
    }

}
