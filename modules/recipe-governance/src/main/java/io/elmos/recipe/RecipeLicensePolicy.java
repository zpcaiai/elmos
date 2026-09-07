package io.elmos.recipe;

import io.elmos.recipe.RecipeModels.*;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;

public final class RecipeLicensePolicy {
    private static final Set<ExecutionContext> COMMERCIAL = EnumSet.of(
            ExecutionContext.ELMOS_COMMERCIAL_SAAS,
            ExecutionContext.ELMOS_MANAGED_PRIVATE_RUNNER,
            ExecutionContext.ELMOS_PRIVATE_DEPLOYMENT,
            ExecutionContext.ELMOS_PROFESSIONAL_SERVICE);
    private static final Set<LicenseType> PERMISSIVE = EnumSet.of(LicenseType.APACHE_2_0, LicenseType.MIT,
            LicenseType.BSD, LicenseType.ELMOS_COMMERCIAL, LicenseType.ELMOS_COMMUNITY,
            LicenseType.CUSTOMER_OWNED, LicenseType.CUSTOMER_AUTHORIZED,
            LicenseType.THIRD_PARTY_COMMERCIAL_LICENSED);

    private final Catalog catalog;
    private final List<CommercialGrant> grants;

    public RecipeLicensePolicy(Catalog catalog, List<CommercialGrant> grants) {
        this.catalog = Objects.requireNonNull(catalog);
        this.grants = List.copyOf(grants);
    }

    public LicenseDecision evaluate(String recipeName, ExecutionContext context, String policyVersion, Instant at) {
        List<String> evidence = new ArrayList<>();
        Set<String> visiting = new LinkedHashSet<>(), visited = new LinkedHashSet<>();
        DecisionState state = evaluateRecipe(recipeName, context, at, visiting, visited, evidence);
        String decisionId = "license-" + digest(recipeName + "\n" + context + "\n" + policyVersion + "\n" + state.reason);
        return new LicenseDecision(decisionId, recipeName, context, state.license, state.outcome,
                state.reason, policyVersion, at, evidence);
    }

    private DecisionState evaluateRecipe(String recipeName, ExecutionContext context, Instant at,
                                         Set<String> visiting, Set<String> visited, List<String> evidence) {
        if (!visiting.add(recipeName)) return blocked(LicenseType.CONFLICTING, "RECIPE_COMPOSITION_CYCLE");
        Descriptor descriptor = catalog.descriptors().get(recipeName);
        if (descriptor == null) return blocked(LicenseType.UNKNOWN, "RECIPE_LICENSE_UNKNOWN");
        evidence.add("catalog://" + catalog.version() + "/" + recipeName);
        DecisionState own = evaluateArtifact(descriptor.artifact(), context, at, evidence);
        if (!own.permits()) return own;
        for (Artifact dependency : flattenArtifacts(descriptor.artifact().dependencies())) {
            DecisionState childArtifact = evaluateArtifact(dependency, context, at, evidence);
            if (!childArtifact.permits()) return blocked(childArtifact.license, "RECIPE_ARTIFACT_DEPENDENCY_LICENSE_BLOCKED");
        }
        for (String child : descriptor.childRecipes()) {
            DecisionState childState = evaluateRecipe(child, context, at, visiting, visited, evidence);
            if (!childState.permits()) return blocked(childState.license, "RECIPE_CHILD_LICENSE_BLOCKED:" + child);
        }
        visiting.remove(recipeName); visited.add(recipeName);
        return own;
    }

    private DecisionState evaluateArtifact(Artifact artifact, ExecutionContext context, Instant at, List<String> evidence) {
        LicenseType license = artifact.license();
        evidence.add("artifact://" + artifact.coordinate() + "@" + artifact.sha256());
        if (license == LicenseType.UNKNOWN) return blocked(license, "RECIPE_LICENSE_UNKNOWN");
        if (license == LicenseType.CONFLICTING) return blocked(license, "RECIPE_LICENSE_CONFLICT");
        Optional<CommercialGrant> grant = grants.stream().filter(value -> value.permits(artifact, context, at)).findFirst();
        if (grant.isPresent()) {
            evidence.add("grant://" + grant.get().grantId() + "@" + grant.get().documentHash());
            return new DecisionState(license, LicenseOutcome.ALLOWED_WITH_COMMERCIAL_GRANT, "COMMERCIAL_GRANT_ACTIVE");
        }
        if (COMMERCIAL.contains(context) && license == LicenseType.MODERNE_SOURCE_AVAILABLE)
            return blocked(license, context == ExecutionContext.ELMOS_PROFESSIONAL_SERVICE
                    ? "RECIPE_LICENSE_PROFESSIONAL_SERVICE_BLOCKED" : "RECIPE_LICENSE_MANAGED_SERVICE_BLOCKED");
        if (COMMERCIAL.contains(context) && license == LicenseType.MODERNE_PROPRIETARY)
            return blocked(license, "RECIPE_PROPRIETARY_LICENSE_REQUIRED");
        if (PERMISSIVE.contains(license)) return new DecisionState(license, LicenseOutcome.ALLOWED_WITH_ATTRIBUTION, "PERMISSIVE_LICENSE_ALLOWED");
        if (context == ExecutionContext.CUSTOMER_INTERNAL_SELF_MANAGED && license == LicenseType.MODERNE_SOURCE_AVAILABLE)
            return new DecisionState(license, LicenseOutcome.CUSTOMER_REVIEW_REQUIRED, "CUSTOMER_SELF_USE_REQUIRES_LEGAL_REVIEW");
        if (context == ExecutionContext.DEVELOPMENT_AND_TEST && license == LicenseType.MODERNE_SOURCE_AVAILABLE)
            return new DecisionState(license, LicenseOutcome.LEGAL_REVIEW_REQUIRED, "DEVELOPMENT_USE_REQUIRES_REVIEW");
        return blocked(license, "RECIPE_LICENSE_CONTEXT_NOT_ALLOWED");
    }

    private static List<Artifact> flattenArtifacts(List<Artifact> roots) {
        List<Artifact> result = new ArrayList<>();
        Deque<Artifact> remaining = new ArrayDeque<>(roots);
        Set<String> seen = new HashSet<>();
        while (!remaining.isEmpty()) {
            Artifact next = remaining.removeFirst();
            if (seen.add(next.coordinate() + "@" + next.sha256())) {
                result.add(next); remaining.addAll(next.dependencies());
            }
        }
        return result;
    }

    private static DecisionState blocked(LicenseType license, String reason) {
        return new DecisionState(license, LicenseOutcome.BLOCKED, reason);
    }

    private record DecisionState(LicenseType license, LicenseOutcome outcome, String reason) {
        boolean permits() { return outcome == LicenseOutcome.ALLOWED || outcome == LicenseOutcome.ALLOWED_WITH_ATTRIBUTION
                || outcome == LicenseOutcome.ALLOWED_WITH_COMMERCIAL_GRANT; }
    }

    private static String digest(String value) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8))).substring(0, 24); }
        catch (Exception error) { throw new IllegalStateException(error); }
    }
}
