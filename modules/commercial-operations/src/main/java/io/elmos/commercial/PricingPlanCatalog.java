package io.elmos.commercial;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.io.InputStream;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.util.List;
import java.util.Objects;
import java.util.stream.StreamSupport;

/**
 * Versioned, fail-closed CNY self-service catalog.
 *
 * <p>The canonical artifact is
 * {@code contracts/pricing-catalog-schema/elmos-cny-self-serve-v1.json}. Maven
 * packages that exact file as a classpath resource so the Java and web
 * runtimes cannot silently maintain different prices or allowances.</p>
 */
public final class PricingPlanCatalog {
    public static final String CATALOG_VERSION = "2026-07-28.2";
    private static final String RESOURCE = "/pricing/elmos-cny-self-serve-v1.json";
    private static final ObjectMapper JSON = new ObjectMapper();

    public enum CatalogStatus { DRAFT, PUBLISHED, SUPERSEDED }
    public enum BillingPeriod { TRIAL, MONTH, YEAR }
    public enum AllowanceWindow { TRIAL_TERM, MONTHLY }
    public enum AllowanceScope { ORGANIZATION, ACTOR }
    public enum MeterKind { MODEL_TOKEN, PLATFORM_CREDIT }
    public enum TokenClass { INPUT, OUTPUT, CACHE_READ, CACHE_WRITE }
    public enum UsageDecisionType { ALLOW, DENY_TOKEN_LIMIT, DENY_CREDIT_LIMIT }

    public record Money(String currency, BigDecimal amount) {
        public Money {
            require(currency, "currency");
            if (amount == null || amount.signum() < 0 || amount.scale() != 2) {
                throw new IllegalArgumentException("money must be non-negative with exactly two decimals");
            }
        }
    }

    public record Allowance(BigDecimal modelTokens, BigDecimal platformCredits,
                            AllowanceWindow window, boolean rollover) {
        public Allowance {
            modelTokens = quantity(modelTokens, "modelTokens");
            platformCredits = quantity(platformCredits, "platformCredits");
            Objects.requireNonNull(window, "window");
        }
    }

    public record Plan(String planId, String displayName, String eyebrow, String description,
                       BillingPeriod billingPeriod, Money price, String billingLabel,
                       Money effectiveMonthlyPrice, int termDays, Allowance allowance,
                       BigDecimal annualTokenCeiling, BigDecimal annualCreditCeiling,
                       int activeProjects, int concurrentJobs, int artifactRetentionDays,
                       boolean featured, String trialEligibilityPolicy, List<String> features) {
        public Plan {
            require(planId, "planId");
            require(displayName, "displayName");
            require(eyebrow, "eyebrow");
            require(description, "description");
            require(billingLabel, "billingLabel");
            require(trialEligibilityPolicy, "trialEligibilityPolicy");
            Objects.requireNonNull(billingPeriod, "billingPeriod");
            Objects.requireNonNull(price, "price");
            Objects.requireNonNull(effectiveMonthlyPrice, "effectiveMonthlyPrice");
            Objects.requireNonNull(allowance, "allowance");
            annualTokenCeiling = quantity(annualTokenCeiling, "annualTokenCeiling");
            annualCreditCeiling = quantity(annualCreditCeiling, "annualCreditCeiling");
            if (termDays <= 0 || activeProjects <= 0 || concurrentJobs <= 0
                    || artifactRetentionDays <= 0) {
                throw new IllegalArgumentException("plan limits must be positive");
            }
            features = List.copyOf(features);
        }
    }

    public record TokenClassDefinition(TokenClass tokenClass, String unit,
                                       boolean providerReceiptRequired) {
        public TokenClassDefinition {
            Objects.requireNonNull(tokenClass, "tokenClass");
            require(unit, "unit");
            if (!providerReceiptRequired) {
                throw new IllegalArgumentException("provider receipts are mandatory");
            }
        }
    }

    public record MeterDefinition(String meterId, MeterKind kind, String unit,
                                  String aggregation, String debitRule,
                                  List<CreditRate> creditRates) {
        public MeterDefinition {
            require(meterId, "meterId");
            require(unit, "unit");
            require(aggregation, "aggregation");
            require(debitRule, "debitRule");
            Objects.requireNonNull(kind, "kind");
            creditRates = List.copyOf(creditRates);
        }
    }

    public record CreditRate(String operationKey, String label, BigDecimal credits,
                             String unit, String meterVersion) {
        public CreditRate {
            require(operationKey, "operationKey");
            require(label, "label");
            require(unit, "unit");
            require(meterVersion, "meterVersion");
            credits = positiveQuantity(credits, "credits");
        }
    }

    public record UsageDecision(UsageDecisionType decision, String planId,
                                BigDecimal requestedTokens, BigDecimal requestedCredits,
                                BigDecimal remainingTokens, BigDecimal remainingCredits,
                                List<String> reasonCodes) {
        public UsageDecision {
            Objects.requireNonNull(decision, "decision");
            require(planId, "planId");
            requestedTokens = quantity(requestedTokens, "requestedTokens");
            requestedCredits = quantity(requestedCredits, "requestedCredits");
            remainingTokens = quantity(remainingTokens, "remainingTokens");
            remainingCredits = quantity(remainingCredits, "remainingCredits");
            reasonCodes = List.copyOf(reasonCodes);
        }
    }

    public record Catalog(String schemaVersion, String catalogVersion, CatalogStatus status,
                          String currency, Instant effectiveFrom, Instant effectiveUntil,
                          String authoritativeSource, String sellerLegalEntityStatus,
                          String taxStatus, String taxPresentation, String paymentStatus,
                          String paymentProvider, String costValidationStatus,
                          String overagePolicy, AllowanceScope allowanceScope,
                          List<Plan> plans, List<TokenClassDefinition> tokenClasses,
                          List<CreditRate> creditRates, List<MeterDefinition> meters,
                          List<String> limitations) {
        public Catalog {
            require(schemaVersion, "schemaVersion");
            require(catalogVersion, "catalogVersion");
            require(currency, "currency");
            require(authoritativeSource, "authoritativeSource");
            require(sellerLegalEntityStatus, "sellerLegalEntityStatus");
            require(taxStatus, "taxStatus");
            require(taxPresentation, "taxPresentation");
            require(paymentStatus, "paymentStatus");
            require(paymentProvider, "paymentProvider");
            require(costValidationStatus, "costValidationStatus");
            require(overagePolicy, "overagePolicy");
            Objects.requireNonNull(status, "status");
            Objects.requireNonNull(effectiveFrom, "effectiveFrom");
            Objects.requireNonNull(allowanceScope, "allowanceScope");
            plans = List.copyOf(plans);
            tokenClasses = List.copyOf(tokenClasses);
            creditRates = List.copyOf(creditRates);
            meters = List.copyOf(meters);
            limitations = List.copyOf(limitations);
        }
    }

    private static final Catalog CHINA_SELF_SERVE_DRAFT = loadCatalog();

    private PricingPlanCatalog() {}

    public static Catalog chinaSelfServeDraft() {
        return CHINA_SELF_SERVE_DRAFT;
    }

    public static Plan requirePlan(String planId) {
        return CHINA_SELF_SERVE_DRAFT.plans().stream()
                .filter(plan -> plan.planId().equals(planId))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("unknown pricing plan"));
    }

    public static void requireOrderable() {
        if (CHINA_SELF_SERVE_DRAFT.status() != CatalogStatus.PUBLISHED
                || !"CONFIGURED".equals(CHINA_SELF_SERVE_DRAFT.sellerLegalEntityStatus())
                || !"CONFIGURED".equals(CHINA_SELF_SERVE_DRAFT.taxStatus())
                || !"CONFIGURED".equals(CHINA_SELF_SERVE_DRAFT.paymentStatus())
                || !"VALIDATED".equals(CHINA_SELF_SERVE_DRAFT.costValidationStatus())) {
            throw new IllegalStateException("pricing catalog is not orderable");
        }
    }

    /**
     * Deterministic preview only. Authoritative admission uses a database
     * reservation transaction and never trusts caller-provided consumption.
     */
    public static UsageDecision previewUsage(String planId, BigDecimal consumedTokens,
                                             BigDecimal consumedCredits, BigDecimal requestedTokens,
                                             BigDecimal requestedCredits) {
        var plan = requirePlan(planId);
        var usedTokens = quantity(consumedTokens, "consumedTokens");
        var usedCredits = quantity(consumedCredits, "consumedCredits");
        var tokenRequest = quantity(requestedTokens, "requestedTokens");
        var creditRequest = quantity(requestedCredits, "requestedCredits");
        var remainingTokens = plan.allowance().modelTokens().subtract(usedTokens).max(BigDecimal.ZERO);
        var remainingCredits = plan.allowance().platformCredits().subtract(usedCredits).max(BigDecimal.ZERO);

        if (tokenRequest.compareTo(remainingTokens) > 0) {
            return new UsageDecision(UsageDecisionType.DENY_TOKEN_LIMIT, planId, tokenRequest,
                    creditRequest, remainingTokens, remainingCredits, List.of("TOKEN_ALLOWANCE_EXCEEDED"));
        }
        if (creditRequest.compareTo(remainingCredits) > 0) {
            return new UsageDecision(UsageDecisionType.DENY_CREDIT_LIMIT, planId, tokenRequest,
                    creditRequest, remainingTokens, remainingCredits, List.of("CREDIT_ALLOWANCE_EXCEEDED"));
        }
        return new UsageDecision(UsageDecisionType.ALLOW, planId, tokenRequest, creditRequest,
                remainingTokens.subtract(tokenRequest), remainingCredits.subtract(creditRequest), List.of());
    }

    public static BigDecimal priceCredits(String operationKey, BigDecimal requestedQuantity) {
        require(operationKey, "operationKey");
        var exactQuantity = quantity(requestedQuantity, "quantity");
        var rate = CHINA_SELF_SERVE_DRAFT.creditRates().stream()
                .filter(candidate -> candidate.operationKey().equals(operationKey))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("unknown credit operation"));
        return rate.credits().multiply(exactQuantity);
    }

    private static Catalog loadCatalog() {
        try (InputStream stream = PricingPlanCatalog.class.getResourceAsStream(RESOURCE)) {
            if (stream == null) throw new IllegalStateException("pricing catalog resource is missing");
            JsonNode root = JSON.readTree(stream);
            String version = text(root, "catalogVersion");
            if (!CATALOG_VERSION.equals(version)) {
                throw new IllegalStateException("pricing catalog version does not match compiled contract");
            }
            String currency = text(root, "currency");
            List<Plan> plans = stream(root.path("plans")).map(node -> plan(node, currency)).toList();
            List<TokenClassDefinition> tokenClasses = stream(root.path("tokenClasses"))
                    .map(node -> new TokenClassDefinition(
                            TokenClass.valueOf(text(node, "tokenClass")),
                            text(node, "unit"),
                            node.path("providerReceiptRequired").asBoolean(false)))
                    .toList();
            List<CreditRate> creditRates = stream(root.path("creditRates"))
                    .map(PricingPlanCatalog::creditRate)
                    .toList();
            List<MeterDefinition> meters = List.of(
                    new MeterDefinition(
                            "model-token-v1",
                            MeterKind.MODEL_TOKEN,
                            "token",
                            "SUM",
                            "provider-confirmed token classes",
                            List.of()),
                    new MeterDefinition(
                            "platform-credit-v1",
                            MeterKind.PLATFORM_CREDIT,
                            "credit",
                            "SUM",
                            "accepted immutable operation usage events",
                            creditRates)
            );
            return new Catalog(
                    text(root, "schemaVersion"),
                    version,
                    CatalogStatus.valueOf(text(root, "status")),
                    currency,
                    Instant.parse(text(root, "effectiveFrom")),
                    nullableInstant(root.get("effectiveUntil")),
                    text(root, "authoritativeSource"),
                    text(root, "sellerLegalEntityStatus"),
                    text(root, "taxStatus"),
                    text(root, "taxPresentation"),
                    text(root, "paymentStatus"),
                    text(root, "paymentProvider"),
                    text(root, "costValidationStatus"),
                    text(root, "overagePolicy"),
                    AllowanceScope.valueOf(text(root, "allowanceScope")),
                    plans,
                    tokenClasses,
                    creditRates,
                    meters,
                    stream(root.path("limitations")).map(JsonNode::asText).toList()
            );
        } catch (IOException error) {
            throw new IllegalStateException("pricing catalog cannot be loaded", error);
        }
    }

    private static Plan plan(JsonNode node, String currency) {
        return new Plan(
                text(node, "planId"),
                text(node, "name"),
                text(node, "eyebrow"),
                text(node, "description"),
                BillingPeriod.valueOf(text(node, "billingPeriod")),
                money(currency, node.path("priceFen").longValue()),
                text(node, "billingLabel"),
                money(currency, node.path("effectiveMonthlyFen").longValue()),
                positiveInt(node, "termDays"),
                new Allowance(
                        integer(node, "tokens"),
                        integer(node, "credits"),
                        AllowanceWindow.valueOf(text(node, "allowanceWindow")),
                        false),
                integer(node, "annualTokens"),
                integer(node, "annualCredits"),
                positiveInt(node, "activeProjects"),
                positiveInt(node, "concurrentJobs"),
                positiveInt(node, "artifactRetentionDays"),
                node.path("featured").asBoolean(false),
                text(node, "trialEligibilityPolicy"),
                stream(node.path("features")).map(JsonNode::asText).toList()
        );
    }

    private static CreditRate creditRate(JsonNode node) {
        return new CreditRate(
                text(node, "operationKey"),
                text(node, "label"),
                integer(node, "credits"),
                text(node, "unit"),
                text(node, "meterVersion")
        );
    }

    private static java.util.stream.Stream<JsonNode> stream(JsonNode array) {
        if (!array.isArray()) throw new IllegalStateException("catalog array is missing");
        return StreamSupport.stream(array.spliterator(), false);
    }

    private static Instant nullableInstant(JsonNode node) {
        return node == null || node.isNull() ? null : Instant.parse(node.asText());
    }

    private static String text(JsonNode node, String field) {
        JsonNode value = node.path(field);
        if (!value.isTextual() || value.asText().isBlank()) {
            throw new IllegalStateException("catalog field is missing: " + field);
        }
        return value.asText();
    }

    private static int positiveInt(JsonNode node, String field) {
        int value = node.path(field).asInt(0);
        if (value <= 0) throw new IllegalStateException("catalog field must be positive: " + field);
        return value;
    }

    private static Money money(String currency, long fen) {
        if (fen < 0) throw new IllegalStateException("catalog money cannot be negative");
        return new Money(currency, BigDecimal.valueOf(fen, 2).setScale(2, RoundingMode.UNNECESSARY));
    }

    private static BigDecimal integer(JsonNode node, String field) {
        JsonNode value = node.path(field);
        if (!value.canConvertToLong() || value.longValue() < 0) {
            throw new IllegalStateException("catalog quantity is invalid: " + field);
        }
        return BigDecimal.valueOf(value.longValue());
    }

    private static BigDecimal positiveQuantity(BigDecimal value, String field) {
        BigDecimal exact = quantity(value, field);
        if (exact.signum() <= 0) throw new IllegalArgumentException(field + " must be positive");
        return exact;
    }

    private static BigDecimal quantity(BigDecimal value, String field) {
        if (value == null || value.scale() > 0 || value.signum() < 0) {
            throw new IllegalArgumentException(field + " must be a non-negative integer");
        }
        return value;
    }

    private static void require(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " is required");
        }
    }
}
