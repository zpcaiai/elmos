package io.elmos.commercial;

import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;

/**
 * Draft, self-serve CNY catalog for the ELMOS customer experience.
 *
 * <p>The catalog is intentionally separate from payment, invoicing and revenue
 * records. It can be inspected by product surfaces, but cannot fulfill an order
 * while the seller legal entity, tax treatment and payment provider remain
 * unconfigured.</p>
 */
public final class PricingPlanCatalog {
    public static final String CATALOG_VERSION = "2026-07-28.1";

    public enum CatalogStatus { DRAFT, PUBLISHED, SUPERSEDED }
    public enum BillingPeriod { TRIAL, MONTH, YEAR }
    public enum AllowanceWindow { TRIAL_TERM, MONTHLY }
    public enum MeterKind { MODEL_TOKEN, PLATFORM_CREDIT }
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
            if (modelTokens == null || platformCredits == null
                    || modelTokens.scale() > 0 || platformCredits.scale() > 0
                    || modelTokens.signum() < 0 || platformCredits.signum() < 0
                    || window == null) {
                throw new IllegalArgumentException("allowance quantities must be non-negative integers");
            }
        }
    }

    public record Plan(String planId, String displayName, BillingPeriod billingPeriod,
                       Money price, int termDays, Allowance allowance,
                       BigDecimal annualTokenCeiling, BigDecimal annualCreditCeiling,
                       int activeProjects, int concurrentJobs, int artifactRetentionDays,
                       List<String> features) {
        public Plan {
            require(planId, "planId");
            require(displayName, "displayName");
            Objects.requireNonNull(billingPeriod, "billingPeriod");
            Objects.requireNonNull(price, "price");
            Objects.requireNonNull(allowance, "allowance");
            if (termDays <= 0 || activeProjects <= 0 || concurrentJobs <= 0
                    || artifactRetentionDays <= 0) {
                throw new IllegalArgumentException("plan limits must be positive");
            }
            if (annualTokenCeiling == null || annualCreditCeiling == null
                    || annualTokenCeiling.scale() > 0 || annualCreditCeiling.scale() > 0
                    || annualTokenCeiling.signum() < 0 || annualCreditCeiling.signum() < 0) {
                throw new IllegalArgumentException("annual ceilings must be non-negative integers");
            }
            features = List.copyOf(features);
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

    public record CreditRate(String operationKey, BigDecimal credits, String unit) {
        public CreditRate {
            require(operationKey, "operationKey");
            require(unit, "unit");
            if (credits == null || credits.scale() > 0 || credits.signum() <= 0) {
                throw new IllegalArgumentException("credit rates must be positive integers");
            }
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
                          String currency, String sellerLegalEntityStatus, String taxStatus,
                          String paymentStatus, String overagePolicy, List<Plan> plans,
                          List<MeterDefinition> meters, List<String> limitations) {
        public Catalog {
            require(schemaVersion, "schemaVersion");
            require(catalogVersion, "catalogVersion");
            require(currency, "currency");
            require(sellerLegalEntityStatus, "sellerLegalEntityStatus");
            require(taxStatus, "taxStatus");
            require(paymentStatus, "paymentStatus");
            require(overagePolicy, "overagePolicy");
            Objects.requireNonNull(status, "status");
            plans = List.copyOf(plans);
            meters = List.copyOf(meters);
            limitations = List.copyOf(limitations);
        }
    }

    private static final Catalog CHINA_SELF_SERVE_DRAFT = new Catalog(
            "1.0.0",
            CATALOG_VERSION,
            CatalogStatus.DRAFT,
            "CNY",
            "NOT_CONFIGURED",
            "NOT_CONFIGURED",
            "NOT_CONFIGURED",
            "HARD_STOP_NO_AUTOMATIC_CHARGE",
            List.of(
                    new Plan(
                            "elmos-free-trial",
                            "免费体验",
                            BillingPeriod.TRIAL,
                            cny("0.00"),
                            14,
                            allowance("2000000", "60", AllowanceWindow.TRIAL_TERM),
                            integer("2000000"),
                            integer("60"),
                            1,
                            1,
                            7,
                            List.of("无需绑定银行卡", "标准模型与核心工作流", "一次完整的小型项目体验")
                    ),
                    new Plan(
                            "elmos-pro-monthly",
                            "专业月付",
                            BillingPeriod.MONTH,
                            cny("129.00"),
                            31,
                            allowance("20000000", "600", AllowanceWindow.MONTHLY),
                            integer("240000000"),
                            integer("7200"),
                            10,
                            3,
                            30,
                            List.of("完整模型目录", "迁移、转换与项目生成", "邮件支持")
                    ),
                    new Plan(
                            "elmos-pro-annual",
                            "专业年付",
                            BillingPeriod.YEAR,
                            cny("1290.00"),
                            365,
                            allowance("25000000", "750", AllowanceWindow.MONTHLY),
                            integer("300000000"),
                            integer("9000"),
                            25,
                            5,
                            90,
                            List.of("月付档全部能力", "每月额度提高 25%", "优先支持与更长证据保留")
                    )
            ),
            List.of(
                    new MeterDefinition(
                            "model-token-v1",
                            MeterKind.MODEL_TOKEN,
                            "token",
                            "SUM",
                            "accepted_input_tokens + accepted_output_tokens",
                            List.of()
                    ),
                    new MeterDefinition(
                            "platform-credit-v1",
                            MeterKind.PLATFORM_CREDIT,
                            "credit",
                            "SUM",
                            "sum of accepted immutable operation usage events",
                            List.of(
                                    rate("repository-discovery", "5", "次"),
                                    rate("migration-or-translation-plan", "15", "次"),
                                    rate("verified-generation-or-migration", "40", "次"),
                                    rate("isolated-runner-minute", "1", "分钟"),
                                    rate("evidence-pack-verification", "10", "次")
                            )
                    )
            ),
            List.of(
                    "Tokens and credits do not roll over.",
                    "Annual allowances refill monthly; annual ceilings are display and contract bounds.",
                    "Missing, late or unreconciled provider usage is not treated as zero.",
                    "Checkout, tax, invoicing and payment execution are NOT_CONFIGURED."
            )
    );

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
                || !"CONFIGURED".equals(CHINA_SELF_SERVE_DRAFT.paymentStatus())) {
            throw new IllegalStateException("pricing catalog is not orderable");
        }
    }

    /**
     * Deterministic allowance preview for one trial or monthly allowance window.
     *
     * <p>This method does not create a usage fact or charge. The caller must
     * persist accepted usage events and reconcile provider receipts before an
     * authoritative debit can be claimed.</p>
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

    public static BigDecimal priceCredits(String operationKey, BigDecimal quantity) {
        require(operationKey, "operationKey");
        var exactQuantity = quantity(quantity, "quantity");
        var rate = CHINA_SELF_SERVE_DRAFT.meters().stream()
                .flatMap(meter -> meter.creditRates().stream())
                .filter(candidate -> candidate.operationKey().equals(operationKey))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("unknown credit operation"));
        return rate.credits().multiply(exactQuantity);
    }

    private static Money cny(String amount) {
        return new Money("CNY", new BigDecimal(amount));
    }

    private static Allowance allowance(String tokens, String credits, AllowanceWindow window) {
        return new Allowance(integer(tokens), integer(credits), window, false);
    }

    private static CreditRate rate(String operationKey, String credits, String unit) {
        return new CreditRate(operationKey, integer(credits), unit);
    }

    private static BigDecimal integer(String value) {
        return new BigDecimal(value);
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
