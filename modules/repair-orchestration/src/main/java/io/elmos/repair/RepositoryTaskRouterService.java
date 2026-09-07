package io.elmos.repair;

import com.fasterxml.jackson.databind.JsonNode;
import io.elmos.repair.RepositoryTaskRouterModels.CanonicalModel;
import io.elmos.repair.RepositoryTaskRouterModels.Catalog;
import io.elmos.repair.RepositoryTaskRouterModels.CostReadiness;
import io.elmos.repair.RepositoryTaskRouterModels.EvidenceState;
import io.elmos.repair.RepositoryTaskRouterModels.Limits;
import io.elmos.repair.RepositoryTaskRouterModels.ModelDescriptor;
import io.elmos.repair.RepositoryTaskRouterModels.OperatorRuntimeProfile;
import io.elmos.repair.RepositoryTaskRouterModels.ParsedSelection;
import io.elmos.repair.RepositoryTaskRouterModels.PreflightResult;
import io.elmos.repair.RepositoryTaskRouterModels.Pricing;
import io.elmos.repair.RepositoryTaskRouterModels.RiskProfile;
import io.elmos.repair.RepositoryTaskRouterModels.SelectionSnapshot;
import io.elmos.repair.RepositoryTaskRouterModels.TaskDagReadiness;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/**
 * Fail-closed catalog and preflight service for repository task routing.
 *
 * <p>This class does not expose an execution authority. A successful future
 * preflight can only prepare task decomposition; it cannot invoke a provider,
 * create a run, mutate a workspace, or perform an SCM operation.</p>
 */
public final class RepositoryTaskRouterService {
    public static final String SCHEMA_VERSION = "1.0";
    public static final String CATALOG_VERSION = "repository-model-catalog-v1.1.0";
    public static final String SELECTION_VERSION = "repository-model-selection-v1";

    private static final List<String> SELECTION_MODES = List.of("smart", "manual");
    private static final List<String> OPTIMIZATION_PROFILES =
            List.of("cost_performance", "lowest_cost", "max_quality", "fastest");
    private static final List<String> FALLBACK_POLICIES = List.of("strict", "smart_within_allowlist");
    private static final List<String> VERIFICATION_POLICIES =
            List.of("system_required_verifiers", "selected_model_only");
    private static final Set<String> TRUSTED_SELECTION_SOURCES = Set.of("ui", "api", "cli", "resume");
    private static final Set<String> RISK_LEVELS = Set.of("none", "low", "medium", "high", "critical");
    private static final Set<String> REQUEST_FIELDS = Set.of(
            "schemaVersion", "catalogVersion", "selectionVersion", "mode", "selectedModel",
            "optimizationProfile", "fallbackPolicy", "verificationPolicy", "risk");
    private static final Set<String> RISK_FIELDS = Set.of(
            "security", "dataMigration", "concurrency", "publicContract", "blastRadius", "longHorizon");

    private static final List<CanonicalModel> CANONICAL_MODELS = List.of(
            model("gpt-5.6-sol-max", "GPT-5.6 Sol Max", "openai", "architect_verifier", 5,
                    List.of("L2", "L3", "L4")),
            model("claude-opus-5-max", "Claude Opus 5 Max", "anthropic", "architect_repo_expert", 5,
                    List.of("L3", "L4")),
            model("claude-fable-5", "Claude Fable 5", "anthropic", "long_horizon_migration", 5,
                    List.of("L4")),
            model("grok-4.6", "Grok 4.6", "xai", "terminal_general_worker", 3,
                    List.of("L1", "L2")),
            model("kimi-k3-max", "Kimi K3 Max", "moonshot", "long_context_worker", 2,
                    List.of("L1", "L2")),
            model("glm-5.3-max", "GLM-5.3 Max", "zhipu", "cost_efficient_worker", 1,
                    List.of("L0")),
            model("qwen3.8-max", "Qwen3.8-Max", "alibaba", "cost_efficient_worker", 1,
                    List.of("L0")),
            model("deepseek-v4-pro-0813", "DeepSeek V4 Pro 0813", "deepseek", "backend_algorithm_worker", 1,
                    List.of("L1")),
            model("gemini-3.7-flash-high", "Gemini 3.7 Flash High", "google", "fast_worker", 1,
                    List.of("L0")),
            model("claude-sonnet-5", "Claude Sonnet 5", "anthropic", "balanced_worker_reviewer", 3,
                    List.of("L1", "L2")));

    private static final Map<String, CanonicalModel> MODELS_BY_ALIAS = indexModels();
    private static final EvidenceState NO_SIDE_EFFECT_EVIDENCE = new EvidenceState(
            "NOT_RUN", "NOT_RUN", "NOT_RUN", "NOT_RUN", "NOT_RUN", "NOT_RUN", "NOT_CERTIFIED");
    private static final List<String> REQUIRED_DAG_STAGES = List.of(
            "requirement_normalization",
            "repository_intake",
            "change_impact_analysis",
            "atomic_task_decomposition",
            "task_dag_build",
            "cost_performance_routing",
            "deterministic_validation");

    private final Map<String, OperatorRuntimeProfile> operatorProfiles;
    private final Clock clock;

    public RepositoryTaskRouterService() {
        this(Map.of(), Clock.systemUTC());
    }

    /** Accepts only server-constructed operator profiles; controllers never deserialize this map. */
    public RepositoryTaskRouterService(Map<String, OperatorRuntimeProfile> operatorProfiles) {
        this(operatorProfiles, Clock.systemUTC());
    }

    RepositoryTaskRouterService(Map<String, OperatorRuntimeProfile> operatorProfiles, Clock clock) {
        Objects.requireNonNull(operatorProfiles, "operatorProfiles");
        Set<String> unknown = new LinkedHashSet<>(operatorProfiles.keySet());
        unknown.removeAll(MODELS_BY_ALIAS.keySet());
        if (!unknown.isEmpty()) {
            throw new IllegalArgumentException("operator profile contains unknown aliases: " + unknown);
        }
        this.operatorProfiles = Map.copyOf(operatorProfiles);
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    public Catalog catalog() {
        List<ModelDescriptor> models = CANONICAL_MODELS.stream().map(this::descriptor).toList();
        long configured = models.stream().filter(ModelDescriptor::available).count();
        List<String> reasons = configured == models.size()
                ? List.of()
                : List.of(
                        "OPERATOR_RUNTIME_PROFILE_REQUIRED",
                        "PROVIDER_IDS_PRICES_LIMITS_AND_CAPABILITIES_MUST_BE_TRUSTED_SERVER_CONFIG",
                        "CONFIGURED_MODELS=" + configured + "/" + models.size());
        return new Catalog(
                SCHEMA_VERSION,
                CATALOG_VERSION,
                SELECTION_VERSION,
                SELECTION_MODES,
                "smart",
                OPTIMIZATION_PROFILES,
                FALLBACK_POLICIES,
                VERIFICATION_POLICIES,
                models,
                configured == models.size() ? "CONFIGURED" : "NOT_CONFIGURED",
                reasons,
                false,
                NO_SIDE_EFFECT_EVIDENCE);
    }

    public PreflightResult preflight(JsonNode body, String trustedSelectionSource) {
        if (!TRUSTED_SELECTION_SOURCES.contains(trustedSelectionSource)) {
            throw new IllegalArgumentException("trusted selection source is invalid");
        }
        ParsedSelection parsed = parse(body, trustedSelectionSource);
        String minimumTier = parsed.risk() == null ? "L0" : minimumTier(parsed.risk());
        SelectionSnapshot snapshot = snapshot(parsed);
        List<String> reasons = new ArrayList<>(parsed.errors());
        String resolvedModel = null;

        if (parsed.errors().isEmpty()) {
            if ("manual".equals(parsed.mode())) {
                CanonicalModel selected = MODELS_BY_ALIAS.get(parsed.selectedModel());
                if (selected != null && selected.highestTier() < tier(minimumTier)) {
                    reasons.add("MANUAL_MODEL_BELOW_RISK_FLOOR:" + selected.alias() + ":" + minimumTier);
                }
                if (selected != null && !descriptor(selected).available()) {
                    reasons.add("SELECTED_MODEL_NOT_CONFIGURED:" + selected.alias());
                } else if (selected != null && selected.highestTier() >= tier(minimumTier)) {
                    resolvedModel = selected.alias();
                }
            } else {
                resolvedModel = CANONICAL_MODELS.stream()
                        .filter(model -> model.highestTier() >= tier(minimumTier))
                        .filter(model -> descriptor(model).available())
                        .sorted(Comparator.comparingInt(CanonicalModel::relativeCostTier)
                                .thenComparing(CanonicalModel::alias))
                        .map(CanonicalModel::alias)
                        .findFirst()
                        .orElse(null);
                if (resolvedModel == null) {
                    reasons.add("NO_CONFIGURED_MODEL_MEETS_RISK_FLOOR:" + minimumTier);
                }
            }
        }

        boolean invalid = !parsed.errors().isEmpty();
        boolean configurationBlocked = reasons.stream().anyMatch(reason ->
                reason.contains("NOT_CONFIGURED") || reason.startsWith("NO_CONFIGURED_MODEL"));
        String configurationStatus = configurationBlocked
                || (invalid && catalog().status().equals("NOT_CONFIGURED"))
                ? "NOT_CONFIGURED"
                : "CONFIGURED";
        String status = reasons.isEmpty() ? "READY_FOR_TASK_DECOMPOSITION" : "BLOCKED";

        String costStatus = "CONFIGURED".equals(configurationStatus) ? "DEFERRED_NOT_RUN" : "NOT_CONFIGURED";
        String costReason = "CONFIGURED".equals(configurationStatus)
                ? "Exact cost requires a decomposed task DAG and token estimates; task decomposition is NOT_RUN."
                : "Exact cost is unavailable until trusted provider prices and limits are configured.";

        List<String> audit = new ArrayList<>();
        audit.add("Selection is version-bound and immutable for this preflight: "
                + (snapshot == null ? "UNAVAILABLE" : snapshot.digest()));
        audit.add("Risk gates are evaluated before cost/performance ranking; minimum tier is " + minimumTier + ".");
        audit.add("Manual strict never switches the primary model; fallback can use only the server allowlist.");
        audit.add("Provider invocation, task decomposition, run creation, workspace mutation, and SCM effects are NOT_RUN.");
        audit.add("This preflight is NOT_CERTIFIED and cannot authorize execution.");

        return new PreflightResult(
                SCHEMA_VERSION,
                CATALOG_VERSION,
                status,
                invalid ? "INVALID" : "VALID",
                configurationStatus,
                reasons,
                snapshot,
                parsed.risk(),
                minimumTier,
                resolvedModel,
                new TaskDagReadiness(
                        "NOT_RUN", REQUIRED_DAG_STAGES, List.of(), List.of(), List.of(),
                        "Preflight validates selection and routing readiness only; no repository task DAG was created."),
                new CostReadiness(
                        costStatus,
                        "USD",
                        null,
                        "invoke_cost + (1-p_success)*expected_escalation_cost + integration_risk_cost + retry_penalty",
                        costReason),
                audit,
                false,
                NO_SIDE_EFFECT_EVIDENCE);
    }

    private ParsedSelection parse(JsonNode body, String trustedSelectionSource) {
        List<String> errors = new ArrayList<>();
        if (body == null || !body.isObject()) {
            errors.add("REQUEST_MUST_BE_JSON_OBJECT");
            return emptyParsed(errors);
        }
        body.fieldNames().forEachRemaining(field -> {
            if (!REQUEST_FIELDS.contains(field)) errors.add("UNSUPPORTED_FIELD:" + field);
        });

        String schemaVersion = requiredText(body, "schemaVersion", errors);
        String catalogVersion = requiredText(body, "catalogVersion", errors);
        String selectionVersion = requiredText(body, "selectionVersion", errors);
        String mode = requiredText(body, "mode", errors);
        String optimization = requiredText(body, "optimizationProfile", errors);
        JsonNode fallbackNode = body.get("fallbackPolicy");
        String callerFallback = null;
        if (fallbackNode == null) {
            errors.add("FALLBACK_POLICY_FIELD_REQUIRED");
        } else if (!fallbackNode.isNull()) {
            if (!fallbackNode.isTextual() || fallbackNode.textValue().isBlank()) {
                errors.add("FALLBACK_POLICY_MUST_BE_POLICY_OR_NULL");
            } else {
                callerFallback = fallbackNode.textValue();
            }
        }
        String verification = requiredText(body, "verificationPolicy", errors);
        boolean locked = "manual".equals(mode);

        if (schemaVersion != null && !SCHEMA_VERSION.equals(schemaVersion)) errors.add("SCHEMA_VERSION_UNSUPPORTED");
        if (catalogVersion != null && !CATALOG_VERSION.equals(catalogVersion)) errors.add("CATALOG_VERSION_STALE");
        if (selectionVersion != null && !SELECTION_VERSION.equals(selectionVersion)) errors.add("SELECTION_VERSION_UNSUPPORTED");
        if (mode != null && !SELECTION_MODES.contains(mode)) errors.add("MODE_INVALID");
        if (optimization != null && !OPTIMIZATION_PROFILES.contains(optimization)) errors.add("OPTIMIZATION_PROFILE_INVALID");
        if (callerFallback != null && !FALLBACK_POLICIES.contains(callerFallback)) errors.add("FALLBACK_POLICY_INVALID");
        if (verification != null && !VERIFICATION_POLICIES.contains(verification)) errors.add("VERIFICATION_POLICY_INVALID");

        JsonNode selectedNode = body.get("selectedModel");
        String selectedModel = null;
        if (selectedNode == null) {
            errors.add("SELECTED_MODEL_FIELD_REQUIRED");
        } else if (!selectedNode.isNull()) {
            if (!selectedNode.isTextual() || selectedNode.textValue().isBlank()) {
                errors.add("SELECTED_MODEL_MUST_BE_ALIAS_OR_NULL");
            } else {
                selectedModel = selectedNode.textValue();
            }
        }
        if ("smart".equals(mode)) {
            if (selectedModel != null) errors.add("SMART_SELECTED_MODEL_MUST_BE_NULL");
            if (callerFallback != null) errors.add("SMART_FALLBACK_POLICY_MUST_BE_NULL");
        }
        if ("manual".equals(mode)) {
            if (selectedModel == null) errors.add("MANUAL_SELECTED_MODEL_REQUIRED");
            else if (!MODELS_BY_ALIAS.containsKey(selectedModel)) errors.add("MODEL_ALIAS_NOT_ALLOWLISTED:" + selectedModel);
            if (callerFallback == null) errors.add("MANUAL_FALLBACK_POLICY_REQUIRED");
        }

        RiskProfile risk = parseRisk(body.get("risk"), errors);
        String resolvedFallback = "smart".equals(mode) ? "router_policy" : callerFallback;
        return new ParsedSelection(
                schemaVersion, catalogVersion, selectionVersion, mode, selectedModel, optimization,
                resolvedFallback, verification, trustedSelectionSource, locked, risk, errors);
    }

    private static RiskProfile parseRisk(JsonNode riskNode, List<String> errors) {
        if (riskNode == null || !riskNode.isObject()) {
            errors.add("RISK_PROFILE_REQUIRED");
            return null;
        }
        riskNode.fieldNames().forEachRemaining(field -> {
            if (!RISK_FIELDS.contains(field)) errors.add("UNSUPPORTED_RISK_FIELD:" + field);
        });
        String security = requiredText(riskNode, "security", errors);
        String dataMigration = requiredText(riskNode, "dataMigration", errors);
        String concurrency = requiredText(riskNode, "concurrency", errors);
        String publicContract = requiredText(riskNode, "publicContract", errors);
        String blastRadius = requiredText(riskNode, "blastRadius", errors);
        Boolean longHorizon = requiredBoolean(riskNode, "longHorizon", errors);
        validateRisk("security", security, errors);
        validateRisk("dataMigration", dataMigration, errors);
        validateRisk("concurrency", concurrency, errors);
        validateRisk("publicContract", publicContract, errors);
        validateRisk("blastRadius", blastRadius, errors);
        if (security == null || dataMigration == null || concurrency == null
                || publicContract == null || blastRadius == null || longHorizon == null) return null;
        return new RiskProfile(security, dataMigration, concurrency, publicContract, blastRadius, longHorizon);
    }

    private static void validateRisk(String field, String value, List<String> errors) {
        if (value != null && !RISK_LEVELS.contains(value)) errors.add("RISK_LEVEL_INVALID:" + field);
    }

    private static String requiredText(JsonNode object, String field, List<String> errors) {
        JsonNode value = object.get(field);
        if (value == null || !value.isTextual() || value.textValue().isBlank()) {
            errors.add("TEXT_FIELD_REQUIRED:" + field);
            return null;
        }
        return value.textValue();
    }

    private static Boolean requiredBoolean(JsonNode object, String field, List<String> errors) {
        JsonNode value = object.get(field);
        if (value == null || !value.isBoolean()) {
            errors.add("BOOLEAN_FIELD_REQUIRED:" + field);
            return null;
        }
        return value.booleanValue();
    }

    private static ParsedSelection emptyParsed(List<String> errors) {
        return new ParsedSelection(null, null, null, null, null, null, null, null, null, null, null, errors);
    }

    private static String minimumTier(RiskProfile risk) {
        if (risk.longHorizon()) return "L4";
        if (atLeastHigh(risk.security())
                || atLeastHigh(risk.dataMigration())
                || atLeastHigh(risk.concurrency())
                || atLeastHigh(risk.publicContract())
                || "critical".equals(risk.blastRadius())) return "L3";
        return "L0";
    }

    private static boolean atLeastHigh(String value) {
        return "high".equals(value) || "critical".equals(value);
    }

    private SelectionSnapshot snapshot(ParsedSelection parsed) {
        if (!parsed.errors().isEmpty()) return null;
        String canonical = String.join("\n",
                parsed.schemaVersion(), parsed.catalogVersion(), parsed.selectionVersion(), parsed.mode(),
                Objects.toString(parsed.selectedModel(), "null"), parsed.optimizationProfile(), parsed.fallbackPolicy(),
                parsed.verificationPolicy(), parsed.selectionSource(), String.valueOf(parsed.lockedByUser()),
                parsed.risk().security(), parsed.risk().dataMigration(), parsed.risk().concurrency(),
                parsed.risk().publicContract(), parsed.risk().blastRadius(), String.valueOf(parsed.risk().longHorizon()));
        return new SelectionSnapshot(
                parsed.schemaVersion(), parsed.catalogVersion(), parsed.selectionVersion(), parsed.mode(),
                parsed.selectedModel(), parsed.optimizationProfile(), parsed.fallbackPolicy(),
                parsed.verificationPolicy(), parsed.selectionSource(), parsed.lockedByUser(), true, sha256(canonical));
    }

    private ModelDescriptor descriptor(CanonicalModel model) {
        OperatorRuntimeProfile profile = operatorProfiles.get(model.alias());
        List<String> reasons = profileReasons(model, profile);
        boolean available = reasons.isEmpty();
        Pricing pricing = new Pricing(
                decimal(profile == null ? null : profile.inputPerMillion()),
                decimal(profile == null ? null : profile.cachedInputPerMillion()),
                decimal(profile == null ? null : profile.outputPerMillion()),
                "USD",
                "operator_or_live_adapter",
                instant(profile == null ? null : profile.pricingEffectiveAt()));
        Limits limits = new Limits(
                profile == null ? null : profile.contextTokens(),
                profile == null ? null : profile.maxOutputTokens(),
                profile == null ? null : profile.concurrency());
        return new ModelDescriptor(
                model.alias(), model.displayName(), model.provider(), model.roleHint(), model.relativeCostTier(),
                model.routingTiers(), "L" + model.highestTier(),
                profile == null || placeholder(profile.providerModelId()) ? null : profile.providerModelId(),
                pricing, limits, profile == null ? Set.of() : profile.capabilities(),
                profile == null ? null : profile.deploymentId(),
                profile == null ? null : profile.exactModelRevision(),
                profile == null ? null : profile.providerGatewayAdapterId(),
                instant(profile == null ? null : profile.observedAt()),
                profile == null ? null : profile.maximumStalenessSeconds(),
                profile == null || profile.quotaRemainingTokens() == null
                        ? null : String.valueOf(profile.quotaRemainingTokens()),
                profile == null ? null : profile.activeConcurrency(),
                profile == null ? Set.of() : profile.residencies(),
                profile == null ? null : profile.privacyPolicyId(),
                profile == null ? null : profile.supportsPrivateRepositories(),
                available ? "AVAILABLE" : "NOT_CONFIGURED", available, available, reasons);
    }

    private List<String> profileReasons(CanonicalModel model, OperatorRuntimeProfile profile) {
        List<String> reasons = new ArrayList<>();
        if (profile == null || placeholder(profile.providerModelId())) reasons.add("PROVIDER_MODEL_ID_UNSET");
        if (profile == null || placeholder(profile.deploymentId())) reasons.add("DEPLOYMENT_ID_UNSET");
        if (profile == null || placeholder(profile.exactModelRevision())) reasons.add("EXACT_MODEL_REVISION_UNSET");
        if (profile == null || placeholder(profile.providerGatewayAdapterId())
                || !profile.providerGatewayAdapterId().startsWith("provider-gateway/")) {
            reasons.add("CANONICAL_PROVIDER_GATEWAY_ADAPTER_UNSET");
        }
        if (profile == null || !profile.enabled()) reasons.add("OPERATOR_PROFILE_DISABLED_OR_UNSET");
        if (profile == null || !profile.liveAvailable()) reasons.add("LIVE_AVAILABILITY_UNCONFIRMED");
        if (profile == null || invalidMoney(profile.inputPerMillion())) reasons.add("INPUT_PRICE_UNSET");
        if (profile == null || invalidMoney(profile.cachedInputPerMillion())) reasons.add("CACHED_INPUT_PRICE_UNSET");
        if (profile == null || invalidMoney(profile.outputPerMillion())) reasons.add("OUTPUT_PRICE_UNSET");
        if (profile == null || invalidPositive(profile.contextTokens())) reasons.add("CONTEXT_LIMIT_UNSET");
        if (profile == null || invalidPositive(profile.maxOutputTokens())) reasons.add("OUTPUT_LIMIT_UNSET");
        if (profile == null || invalidPositive(profile.concurrency())) reasons.add("CONCURRENCY_LIMIT_UNSET");
        if (profile == null || profile.quotaRemainingTokens() == null || profile.quotaRemainingTokens() < 1) {
            reasons.add("LIVE_QUOTA_UNAVAILABLE");
        }
        if (profile == null || profile.activeConcurrency() == null || profile.activeConcurrency() < 0
                || invalidPositive(profile.concurrency())
                || profile.activeConcurrency() >= profile.concurrency()) {
            reasons.add("ACTIVE_CONCURRENCY_UNAVAILABLE");
        }
        if (profile == null || profile.residencies().isEmpty()) reasons.add("RESIDENCY_POLICY_UNSET");
        if (profile == null || placeholder(profile.privacyPolicyId())) reasons.add("PRIVACY_POLICY_UNSET");
        if (profile == null || profile.supportsPrivateRepositories() == null) reasons.add("PRIVATE_REPOSITORY_POLICY_UNSET");
        if (profile == null || !profile.capabilities().contains("repository_task_execution")
                || !profile.capabilities().contains(model.roleHint())) reasons.add("REQUIRED_CAPABILITIES_UNSET");
        if (profile == null || profile.maximumStalenessSeconds() == null
                || profile.maximumStalenessSeconds() < 1 || profile.maximumStalenessSeconds() > 86_400) {
            reasons.add("PROFILE_STALENESS_BOUND_INVALID");
        } else {
            Instant now = clock.instant();
            if (stale(profile.observedAt(), profile.maximumStalenessSeconds(), now)) {
                reasons.add("LIVE_OBSERVATION_STALE_OR_UNSET");
            }
            if (stale(profile.pricingEffectiveAt(), profile.maximumStalenessSeconds(), now)) {
                reasons.add("PRICING_EFFECTIVE_AT_STALE_OR_UNSET");
            }
        }
        return List.copyOf(reasons);
    }

    private static boolean stale(Instant value, int maximumStalenessSeconds, Instant now) {
        return value == null || value.isAfter(now) || value.plusSeconds(maximumStalenessSeconds).isBefore(now);
    }

    private static String decimal(BigDecimal value) {
        return value == null ? null : value.toPlainString();
    }

    private static String instant(Instant value) {
        return value == null ? null : value.toString();
    }

    private static boolean placeholder(String value) {
        return value == null || value.isBlank() || "SET_ME".equals(value.trim().toUpperCase(Locale.ROOT));
    }

    private static boolean invalidMoney(BigDecimal value) {
        return value == null || value.signum() < 0;
    }

    private static boolean invalidPositive(Integer value) {
        return value == null || value < 1;
    }

    private static CanonicalModel model(String alias, String displayName, String provider, String roleHint,
                                        int relativeCostTier, List<String> routingTiers) {
        int highest = routingTiers.stream().mapToInt(RepositoryTaskRouterService::tier).max().orElse(0);
        return new CanonicalModel(alias, displayName, provider, roleHint, relativeCostTier, routingTiers, highest);
    }

    private static Map<String, CanonicalModel> indexModels() {
        Map<String, CanonicalModel> indexed = new LinkedHashMap<>();
        for (CanonicalModel model : CANONICAL_MODELS) {
            if (indexed.put(model.alias(), model) != null) throw new IllegalStateException("duplicate model alias");
        }
        return Map.copyOf(indexed);
    }

    private static int tier(String tier) {
        Integer value = RepositoryTaskRouterModels.TIER_ORDER.get(tier);
        if (value == null) throw new IllegalArgumentException("unknown routing tier: " + tier);
        return value;
    }

    private static String sha256(String value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
            return java.util.HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException("SHA-256 unavailable", error);
        }
    }
}
