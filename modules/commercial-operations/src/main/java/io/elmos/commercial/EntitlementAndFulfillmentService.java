package io.elmos.commercial;

import io.elmos.commercial.CommercialModels.*;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.*;

public final class EntitlementAndFulfillmentService {
    private final Map<String, BigDecimal> consumedByEntitlement = new HashMap<>();
    private final Map<String, FulfillmentEntry> fulfillmentByIdempotencyKey = new HashMap<>();
    private record FulfillmentEntry(CommercialOrder order, FulfillmentResult result) {}

    public EntitlementDecision decide(String organizationId, String featureKey, List<Entitlement> entitlements,
                                      BigDecimal requested, boolean securityRestricted,
                                      boolean contractRestricted, String policyVersion, Instant now) {
        if (requested != null && requested.signum() < 0) throw new IllegalArgumentException("requested entitlement amount must be non-negative");
        if (securityRestricted) return decision(EntitlementDecisionType.DENY_NOT_ENTITLED, organizationId, featureKey,
                BigDecimal.ZERO, List.of(), policyVersion, "SECURITY_RESTRICTION");
        if (contractRestricted) return decision(EntitlementDecisionType.DENY_NOT_ENTITLED, organizationId, featureKey,
                BigDecimal.ZERO, List.of(), policyVersion, "CONTRACT_RESTRICTION");
        List<Entitlement> matching = entitlements.stream()
                .filter(value -> value.organizationId().equals(organizationId) && value.featureKey().equals(featureKey) && value.active())
                .toList();
        if (matching.isEmpty()) return decision(EntitlementDecisionType.DENY_NOT_ENTITLED, organizationId, featureKey,
                BigDecimal.ZERO, List.of(), policyVersion, "FEATURE_NOT_ENTITLED");
        if (matching.stream().anyMatch(value -> value.source() == EntitlementSource.PRIVATE_LICENSE && !value.licenseSignatureValid())) {
            return decision(EntitlementDecisionType.DENY_LICENSE_INVALID, organizationId, featureKey,
                    BigDecimal.ZERO, ids(matching), policyVersion, "LICENSE_SIGNATURE_INVALID");
        }
        List<Entitlement> valid = matching.stream()
                .filter(value -> !now.isBefore(value.validFrom()) && now.isBefore(value.validUntil())).toList();
        if (valid.isEmpty()) {
            return decision(EntitlementDecisionType.DENY_EXPIRED, organizationId, featureKey,
                    BigDecimal.ZERO, ids(matching), policyVersion, "ENTITLEMENT_EXPIRED");
        }
        BigDecimal remaining = valid.stream().map(this::remaining).reduce(BigDecimal.ZERO, BigDecimal::add);
        if (requested != null && remaining.compareTo(requested) < 0) {
            return decision(EntitlementDecisionType.DENY_LIMIT_EXCEEDED, organizationId, featureKey,
                    remaining, ids(matching), policyVersion, "ALLOWANCE_EXCEEDED");
        }
        return decision(EntitlementDecisionType.ALLOW, organizationId, featureKey, remaining,
                ids(valid), policyVersion, "ENTITLEMENT_ACTIVE");
    }

    public synchronized EntitlementDecision consume(String organizationId, String featureKey,
                                                     List<Entitlement> entitlements, BigDecimal requested,
                                                     String policyVersion, Instant now) {
        if (requested == null || requested.signum() <= 0) throw new IllegalArgumentException("consumption amount must be positive");
        EntitlementDecision authorization = decide(organizationId, featureKey, entitlements, requested,
                false, false, policyVersion, now);
        if (authorization.decision() != EntitlementDecisionType.ALLOW) return authorization;
        BigDecimal outstanding = requested;
        Set<String> authorized = Set.copyOf(authorization.sourceEntitlementIds());
        for (Entitlement entitlement : entitlements) {
            if (!authorized.contains(entitlement.entitlementId())) continue;
            BigDecimal available = remaining(entitlement);
            BigDecimal take = available.min(outstanding);
            if (take.signum() > 0) consumedByEntitlement.merge(entitlement.entitlementId(), take, BigDecimal::add);
            outstanding = outstanding.subtract(take);
            if (outstanding.signum() == 0) break;
        }
        return decide(organizationId, featureKey, entitlements, BigDecimal.ZERO, false, false, policyVersion, now);
    }

    public synchronized FulfillmentResult fulfill(CommercialOrder order, Instant now) {
        String scope = order.organizationId() + "\u0000" + order.fulfillmentIdempotencyKey();
        FulfillmentEntry existing = fulfillmentByIdempotencyKey.get(scope);
        if (existing != null) {
            if (!existing.order().equals(order)) throw new IllegalStateException("FULFILLMENT_IDEMPOTENCY_CONFLICT");
            return existing.result();
        }
        if (!Set.of(OrderStatus.ACCEPTED, OrderStatus.FULFILLMENT_PENDING, OrderStatus.FULFILLING).contains(order.status())) {
            throw new IllegalStateException("ORDER_NOT_ACCEPTED_FOR_FULFILLMENT");
        }
        List<Entitlement> entitlements = new ArrayList<>();
        List<FulfillmentTask> tasks = new ArrayList<>();
        List<String> generated = new ArrayList<>();
        for (OrderLine line : order.lines()) {
            if (line.featureKey() != null && !line.featureKey().isBlank()) {
                String entitlementId = "ent-" + stable(order.orderId() + ":" + line.lineId());
                entitlements.add(new Entitlement(entitlementId, order.organizationId(), line.featureKey(),
                        EntitlementSource.ORDER, LimitType.USAGE, line.quantity(), BigDecimal.ZERO,
                        now, now.plusSeconds(366L * 24 * 3600), true, true));
                generated.add(entitlementId);
            }
            switch (line.productType()) {
                case "PRIVATE_LICENSE" -> tasks.add(task(order, line, "GENERATE_SIGNED_OFFLINE_LICENSE", "LICENSE_ADMIN"));
                case "PRIVATE_RUNNER" -> tasks.add(task(order, line, "CREATE_PRIVATE_RUNNER_POOL", "RUNNER_ADMIN"));
                case "IMPLEMENTATION_SERVICE" -> tasks.add(task(order, line, "CREATE_IMPLEMENTATION_WORK_PACKAGE", "MIGRATION_ADMIN"));
                default -> { }
            }
        }
        String subscriptionId = "subscription-" + stable(order.orderId());
        String onboardingId = "onboarding-" + stable(order.orderId());
        generated.add(subscriptionId); generated.add(onboardingId);
        tasks.add(new FulfillmentTask("task-" + stable(order.orderId() + ":onboarding"), "CREATE_ONBOARDING_PLAN",
                "ORGANIZATION_OWNER", List.of("SUBSCRIPTION_CREATED"), List.of(), false));
        OrderStatus status = tasks.stream().allMatch(FulfillmentTask::completed) ? OrderStatus.FULFILLED : OrderStatus.PARTIALLY_FULFILLED;
        FulfillmentResult result = new FulfillmentResult(order.orderId(), status, entitlements, tasks, generated,
                status == OrderStatus.PARTIALLY_FULFILLED ? List.of("HUMAN_FULFILLMENT_TASKS_REMAIN") : List.of());
        fulfillmentByIdempotencyKey.put(scope, new FulfillmentEntry(order, result));
        return result;
    }

    private BigDecimal remaining(Entitlement entitlement) {
        BigDecimal runtimeConsumed = consumedByEntitlement.getOrDefault(entitlement.entitlementId(), BigDecimal.ZERO);
        return entitlement.limit().subtract(entitlement.consumed()).subtract(runtimeConsumed).max(BigDecimal.ZERO);
    }
    private static FulfillmentTask task(CommercialOrder order, OrderLine line, String type, String role) {
        return new FulfillmentTask("task-" + stable(order.orderId() + ":" + line.lineId() + ":" + type),
                type, role, List.of("ORDER_ACCEPTED"), List.of(), false);
    }
    private static List<String> ids(List<Entitlement> values) { return values.stream().map(Entitlement::entitlementId).toList(); }
    private static EntitlementDecision decision(EntitlementDecisionType type, String org, String feature,
                                                BigDecimal remaining, List<String> sources, String policy,
                                                String reason) {
        return new EntitlementDecision(type, org, feature, remaining, sources, policy, List.of(reason));
    }
    private static String stable(String value) {
        try { return java.util.HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256")
                .digest(value.getBytes(java.nio.charset.StandardCharsets.UTF_8))).substring(0, 20); }
        catch (java.security.NoSuchAlgorithmException e) { throw new IllegalStateException(e); }
    }
}
