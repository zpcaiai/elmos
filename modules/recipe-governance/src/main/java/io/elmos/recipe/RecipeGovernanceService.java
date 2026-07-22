package io.elmos.recipe;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.recipe.RecipeModels.*;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;

public final class RecipeGovernanceService {
    private static final Set<String> DYNAMIC_VERSIONS = Set.of("LATEST", "RELEASE", "latest.release", "latest.integration");
    private final Catalog catalog;
    private final RecipeLicensePolicy licenses;
    private final ObjectMapper json;

    public RecipeGovernanceService(Catalog catalog, List<CommercialGrant> grants, ObjectMapper json) {
        this.catalog = Objects.requireNonNull(catalog); this.licenses = new RecipeLicensePolicy(catalog, grants);
        this.json = Objects.requireNonNull(json);
    }

    public Selection select(SelectionRequest request) {
        List<Candidate> ranked = catalog.descriptors().values().stream().map(descriptor -> candidate(descriptor, request))
                .sorted(Comparator.comparingInt(Candidate::score).reversed().thenComparing(Candidate::recipeName)).toList();
        Set<String> missing = new TreeSet<>(request.requiredCapabilities());
        List<String> selected = new ArrayList<>();
        List<Candidate> output = new ArrayList<>();
        Set<String> selectedNames = new LinkedHashSet<>();
        for (Candidate candidate : ranked) {
            boolean useful = candidate.rejectionReasons().isEmpty() && candidate.capabilityCoverage().stream().anyMatch(missing::contains);
            Descriptor descriptor = catalog.descriptors().get(candidate.recipeName());
            boolean conflicts = useful && descriptor.conflictingRecipes().stream().anyMatch(selectedNames::contains);
            List<String> reasons = new ArrayList<>(candidate.rejectionReasons());
            if (conflicts) reasons.add("RECIPE_CONFLICT");
            boolean chosen = useful && !conflicts;
            if (chosen) {
                selected.add(candidate.recipeName()); selectedNames.add(candidate.recipeName());
                missing.removeAll(candidate.capabilityCoverage());
            }
            output.add(new Candidate(candidate.recipeName(), candidate.score(), candidate.capabilityCoverage(), reasons,
                    candidate.licenseDecision(), chosen));
        }
        SelectionStatus status = missing.isEmpty() ? SelectionStatus.SELECTED
                : selected.isEmpty() && output.stream().anyMatch(value -> value.rejectionReasons().stream().anyMatch(reason -> reason.startsWith("RECIPE_LICENSE")))
                ? SelectionStatus.LICENSE_BLOCKED : selected.isEmpty() ? SelectionStatus.NO_RECIPE_FOUND : SelectionStatus.PARTIAL;
        List<String> findings = new ArrayList<>();
        if (!missing.isEmpty()) findings.add("RECIPE_CAPABILITY_PARTIAL:" + String.join(",", missing));
        if (status == SelectionStatus.LICENSE_BLOCKED) findings.add("RECIPE_LICENSE_BLOCKED");
        String selectionId = "selection-" + shortDigest(request.migrationStepId() + "\n" + catalog.version() + "\n"
                + new TreeSet<>(request.requiredCapabilities()) + "\n" + request.sourceVersion() + "\n" + request.targetVersion());
        return new Selection("1.0", selectionId, request.migrationStepId(), catalog.version(),
                request.requiredCapabilities(), output, selected, status, findings);
    }

    public ExecutionManifest buildManifest(Selection selection, String sourceSnapshotId, String sourceCommit,
                                           String targetProfileId, String compatibilitySnapshotId,
                                           String rewriteBomVersion, String pluginVersion,
                                           Map<String,Map<String,Object>> options, RuntimeConfiguration runtime,
                                           int maxCycles, int timeoutSeconds, String policyHash, Instant createdAt) {
        if (selection.status() != SelectionStatus.SELECTED) throw new IllegalStateException("only a complete recipe selection can produce a manifest");
        requirePinned(rewriteBomVersion, "rewriteBomVersion"); requirePinned(pluginVersion, "rewriteMavenPluginVersion");
        List<ResolvedRecipe> recipes = new ArrayList<>(); List<String> decisionIds = new ArrayList<>(); int order = 10;
        for (String name : selection.selectedRecipes()) {
            Descriptor descriptor = catalog.descriptors().get(name);
            Candidate candidate = selection.candidates().stream().filter(value -> value.recipeName().equals(name)).findFirst().orElseThrow();
            if (!candidate.licenseDecision().permitsExecution()) throw new SecurityException("recipe license decision does not permit execution");
            Map<String,Object> configured = options.getOrDefault(name, Map.of()); validateOptions(descriptor, configured);
            requirePinned(descriptor.artifact().version(), "recipeVersion");
            recipes.add(new ResolvedRecipe(name, descriptor.artifact(), configured, order, candidate.licenseDecision().decisionId()));
            decisionIds.add(candidate.licenseDecision().decisionId()); order += 10;
        }
        Map<String,Object> canonical = new TreeMap<>();
        canonical.put("schemaVersion", "1.0"); canonical.put("selectionId", selection.selectionId());
        canonical.put("sourceSnapshotId", sourceSnapshotId); canonical.put("sourceCommit", sourceCommit);
        canonical.put("migrationStepId", selection.migrationStepId()); canonical.put("targetProfileId", targetProfileId);
        canonical.put("compatibilitySnapshotId", compatibilitySnapshotId); canonical.put("rewriteBomVersion", rewriteBomVersion);
        canonical.put("rewriteMavenPluginVersion", pluginVersion); canonical.put("recipes", recipes);
        canonical.put("runtime", runtime); canonical.put("maxCycles", maxCycles); canonical.put("timeoutSeconds", timeoutSeconds);
        canonical.put("exportDataTables", true); canonical.put("licenseDecisionIds", decisionIds);
        canonical.put("policyHash", policyHash); canonical.put("createdAt", createdAt.toString());
        String hash = digest(canonicalJson(canonical)); String manifestId = "manifest-" + hash.substring(0, 24);
        return new ExecutionManifest("1.0", manifestId, sourceSnapshotId, selection.migrationStepId(), sourceCommit,
                targetProfileId, compatibilitySnapshotId, rewriteBomVersion, pluginVersion, recipes, runtime,
                maxCycles, timeoutSeconds, true, decisionIds, policyHash, createdAt, hash);
    }

    public List<String> mavenInvocation(ExecutionManifest manifest) {
        List<String> args = new ArrayList<>(); args.add("mvn"); args.add("-B"); args.add("--no-transfer-progress");
        args.add("org.openrewrite.maven:rewrite-maven-plugin:" + manifest.rewriteMavenPluginVersion() + ":run");
        args.add("-Drewrite.activeRecipes=" + manifest.recipes().stream().map(ResolvedRecipe::recipeName).reduce((a,b) -> a + "," + b).orElseThrow());
        args.add("-Drewrite.recipeArtifactCoordinates=" + manifest.recipes().stream().map(value -> value.artifact().coordinate()).distinct().reduce((a,b) -> a + "," + b).orElseThrow());
        args.add("-Drewrite.exportDatatables=true"); args.add("-Drewrite.activeStyles=");
        return List.copyOf(args);
    }

    private Candidate candidate(Descriptor descriptor, SelectionRequest request) {
        List<String> reasons = new ArrayList<>();
        LicenseDecision license = licenses.evaluate(descriptor.recipeName(), request.executionContext(), request.licensePolicyVersion(), request.evaluatedAt());
        Set<String> coverage = new TreeSet<>(descriptor.capabilities()); coverage.retainAll(request.requiredCapabilities());
        if (coverage.isEmpty()) reasons.add("RECIPE_CAPABILITY_PARTIAL");
        if (!license.permitsExecution()) reasons.add("RECIPE_LICENSE_BLOCKED:" + license.reasonCode());
        if (!descriptor.descriptorValid()) reasons.add("RECIPE_CONFIGURATION_INVALID");
        if (descriptor.promotionStatus() != PromotionStatus.APPROVED) reasons.add("RECIPE_NOT_PROMOTED");
        if (!descriptor.supportedSources().isEmpty() && !descriptor.supportedSources().contains(request.sourceVersion())) reasons.add("RECIPE_SOURCE_TARGET_MISMATCH");
        if (!descriptor.supportedTargets().isEmpty() && !descriptor.supportedTargets().contains(request.targetVersion())) reasons.add("RECIPE_SOURCE_TARGET_MISMATCH");
        if (!pinned(descriptor.artifact().version())) reasons.add("RECIPE_VERSION_NOT_PINNED");
        if (!descriptor.quality().idempotent()) reasons.add("RECIPE_NON_IDEMPOTENT");
        if (!descriptor.quality().regressionVerified()) reasons.add("RECIPE_REGRESSION_NOT_VERIFIED");
        int coverageScore = Math.round(20f * coverage.size() / request.requiredCapabilities().size());
        int score = coverageScore + 15 + (int)Math.round(15 * descriptor.quality().historicalCompletionRate())
                + (descriptor.quality().idempotent() ? 10 : 0) + (descriptor.quality().regressionVerified() ? 10 : 0)
                + descriptor.quality().patchPrecision() / 10 + (descriptor.quality().typeAttributionComplete() ? 10 : 0)
                + descriptor.quality().runtimePerformance() / 20 + descriptor.quality().maintainerConfidence() / 20;
        return new Candidate(descriptor.recipeName(), Math.min(100, score), coverage, reasons, license, false);
    }

    private void validateOptions(Descriptor descriptor, Map<String,Object> configured) {
        if (!descriptor.optionTypes().keySet().containsAll(configured.keySet())) throw new IllegalArgumentException("unknown recipe option");
        for (Map.Entry<String,String> option : descriptor.optionTypes().entrySet()) {
            if (!configured.containsKey(option.getKey())) throw new IllegalArgumentException("required recipe option is missing: " + option.getKey());
            Object value = configured.get(option.getKey()); String expected = option.getValue();
            boolean matches = switch (expected) { case "STRING" -> value instanceof String; case "INTEGER" -> value instanceof Integer;
                case "BOOLEAN" -> value instanceof Boolean; default -> false; };
            if (!matches) throw new IllegalArgumentException("recipe option type mismatch: " + option.getKey());
        }
    }

    private String canonicalJson(Object value) {
        try { return json.writer().with(com.fasterxml.jackson.databind.SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS).writeValueAsString(value); }
        catch (Exception error) { throw new IllegalStateException("manifest canonicalization failed", error); }
    }
    private static boolean pinned(String version) { return version != null && !version.isBlank() && !DYNAMIC_VERSIONS.contains(version)
            && !version.toUpperCase(Locale.ROOT).contains("SNAPSHOT") && !version.contains("+") && !version.contains("[") && !version.contains("("); }
    private static void requirePinned(String value, String field) { if (!pinned(value)) throw new IllegalArgumentException(field + " must be pinned"); }
    private static String shortDigest(String value) { return digest(value).substring(0, 24); }
    static String digest(String value) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8))); }
        catch (Exception error) { throw new IllegalStateException(error); }
    }
}
