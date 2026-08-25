package io.elmos.repair;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * DTOs for the repository task-decomposition and model-routing preflight surface.
 * The surface is deliberately planning-only: it cannot invoke providers, create a
 * run, touch a workspace, or perform source-control operations.
 */
public final class RepositoryTaskRouterModels {
    private RepositoryTaskRouterModels() {}

    public record Pricing(
            String inputPerMillion,
            String cachedInputPerMillion,
            String outputPerMillion,
            String currency,
            String source,
            String effectiveAt) {}

    public record Limits(Integer contextTokens, Integer maxOutputTokens, Integer concurrency) {}

    public record ModelDescriptor(
            String alias,
            String displayName,
            String provider,
            String roleHint,
            int relativeCostTier,
            List<String> routingTiers,
            String highestRoutingTier,
            String providerModelId,
            Pricing pricing,
            Limits limits,
            Set<String> capabilities,
            String deploymentId,
            String exactModelRevision,
            String providerGatewayAdapterId,
            String observedAt,
            Integer profileMaxAgeSeconds,
            String quotaRemainingTokens,
            Integer activeConcurrency,
            Set<String> residencies,
            String privacyPolicyId,
            Boolean supportsPrivateRepositories,
            String status,
            boolean available,
            boolean selectable,
            List<String> reasons) {
        public ModelDescriptor {
            routingTiers = List.copyOf(routingTiers);
            capabilities = Set.copyOf(capabilities);
            residencies = Set.copyOf(residencies);
            reasons = List.copyOf(reasons);
        }
    }

    public record EvidenceState(
            String providerInvocation,
            String taskDecomposition,
            String runCreation,
            String workspaceMutation,
            String scmEffects,
            String externalVerification,
            String certification) {}

    public record Catalog(
            String schemaVersion,
            String catalogVersion,
            String selectionVersion,
            List<String> selectionModes,
            String defaultMode,
            List<String> optimizationProfiles,
            List<String> fallbackPolicies,
            List<String> verificationPolicies,
            List<ModelDescriptor> models,
            String status,
            List<String> reasons,
            boolean runtimeProfilesAcceptedFromClient,
            EvidenceState evidence) {
        public Catalog {
            selectionModes = List.copyOf(selectionModes);
            optimizationProfiles = List.copyOf(optimizationProfiles);
            fallbackPolicies = List.copyOf(fallbackPolicies);
            verificationPolicies = List.copyOf(verificationPolicies);
            models = List.copyOf(models);
            reasons = List.copyOf(reasons);
        }
    }

    public record RiskProfile(
            String security,
            String dataMigration,
            String concurrency,
            String publicContract,
            String blastRadius,
            boolean longHorizon) {}

    public record SelectionSnapshot(
            String schemaVersion,
            String catalogVersion,
            String selectionVersion,
            String mode,
            String selectedModel,
            String optimizationProfile,
            String fallbackPolicy,
            String verificationPolicy,
            String selectionSource,
            boolean lockedByUser,
            boolean immutable,
            String digest) {}

    public record TaskDagReadiness(
            String status,
            List<String> requiredStages,
            List<Object> tasks,
            List<List<String>> waves,
            List<String> criticalPath,
            String reason) {
        public TaskDagReadiness {
            requiredStages = List.copyOf(requiredStages);
            tasks = List.copyOf(tasks);
            waves = waves.stream().map(List::copyOf).toList();
            criticalPath = List.copyOf(criticalPath);
        }
    }

    public record CostReadiness(
            String status,
            String currency,
            String estimatedRunCost,
            String formula,
            String reason) {}

    public record PreflightResult(
            String schemaVersion,
            String catalogVersion,
            String status,
            String validationStatus,
            String configurationStatus,
            List<String> reasons,
            SelectionSnapshot selection,
            RiskProfile risk,
            String minimumRoutingTier,
            String resolvedModel,
            TaskDagReadiness dag,
            CostReadiness cost,
            List<String> auditExplanation,
            boolean runtimeProfilesAcceptedFromClient,
            EvidenceState evidence) {
        public PreflightResult {
            reasons = List.copyOf(reasons);
            auditExplanation = List.copyOf(auditExplanation);
        }

        public boolean invalidRequest() {
            return "INVALID".equals(validationStatus);
        }
    }

    /**
     * Server-trusted configuration seam. It is intentionally absent from every
     * request DTO and controller payload.
     */
    public record OperatorRuntimeProfile(
            String providerModelId,
            String deploymentId,
            String exactModelRevision,
            String providerGatewayAdapterId,
            Instant observedAt,
            Instant pricingEffectiveAt,
            Integer maximumStalenessSeconds,
            boolean enabled,
            boolean liveAvailable,
            BigDecimal inputPerMillion,
            BigDecimal cachedInputPerMillion,
            BigDecimal outputPerMillion,
            Integer contextTokens,
            Integer maxOutputTokens,
            Integer concurrency,
            Long quotaRemainingTokens,
            Integer activeConcurrency,
            Set<String> residencies,
            String privacyPolicyId,
            Boolean supportsPrivateRepositories,
            Set<String> capabilities) {
        public OperatorRuntimeProfile {
            residencies = residencies == null ? Set.of() : Set.copyOf(residencies);
            capabilities = capabilities == null ? Set.of() : Set.copyOf(capabilities);
        }
    }

    record ParsedSelection(
            String schemaVersion,
            String catalogVersion,
            String selectionVersion,
            String mode,
            String selectedModel,
            String optimizationProfile,
            String fallbackPolicy,
            String verificationPolicy,
            String selectionSource,
            Boolean lockedByUser,
            RiskProfile risk,
            List<String> errors) {
        ParsedSelection {
            errors = List.copyOf(errors);
        }
    }

    record CanonicalModel(
            String alias,
            String displayName,
            String provider,
            String roleHint,
            int relativeCostTier,
            List<String> routingTiers,
            int highestTier) {
        CanonicalModel {
            routingTiers = List.copyOf(routingTiers);
        }
    }

    static final Map<String, Integer> TIER_ORDER = Map.of(
            "L0", 0,
            "L1", 1,
            "L2", 2,
            "L3", 3,
            "L4", 4);
}
