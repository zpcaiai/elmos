package io.elmos.recipe;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class RecipeModels {
    private RecipeModels() {}

    public enum LicenseType { APACHE_2_0, MIT, BSD, ELMOS_COMMERCIAL, ELMOS_COMMUNITY,
        CUSTOMER_OWNED, CUSTOMER_AUTHORIZED, THIRD_PARTY_COMMERCIAL_LICENSED,
        MODERNE_SOURCE_AVAILABLE, MODERNE_PROPRIETARY, UNKNOWN, CONFLICTING }
    public enum ExecutionContext { COMMUNITY_LOCAL_SELF_USE, ELMOS_COMMERCIAL_SAAS,
        ELMOS_MANAGED_PRIVATE_RUNNER, ELMOS_PRIVATE_DEPLOYMENT, ELMOS_PROFESSIONAL_SERVICE,
        CUSTOMER_INTERNAL_SELF_MANAGED, DEVELOPMENT_AND_TEST }
    public enum LicenseOutcome { ALLOWED, ALLOWED_WITH_ATTRIBUTION, ALLOWED_WITH_COMMERCIAL_GRANT,
        CUSTOMER_REVIEW_REQUIRED, LEGAL_REVIEW_REQUIRED, BLOCKED }
    public enum PromotionStatus { DRAFT, GENERATED, COMPILED, UNIT_TESTED, IDEMPOTENCE_VERIFIED,
        REGRESSION_VERIFIED, LICENSE_APPROVED, SECURITY_REVIEWED, CANARY, APPROVED, DEPRECATED, BLOCKED }
    public enum SelectionStatus { SELECTED, PARTIAL, NO_RECIPE_FOUND, LICENSE_BLOCKED, INVALID }
    public enum RunStatus { NO_CHANGES, SUCCEEDED_WITH_CHANGES, SUCCEEDED_WITH_WARNINGS, PARSE_FAILED,
        RECIPE_FAILED, POLICY_BLOCKED, TIMED_OUT, RESOURCE_EXCEEDED, CANCELLED }
    public enum IdempotenceStatus { IDEMPOTENT, FIXPOINT_REACHED_AFTER_MULTIPLE_CYCLES,
        NON_IDEMPOTENT, OSCILLATING, STATE_LEAK_SUSPECTED, MAX_CYCLES_EXCEEDED, INCONCLUSIVE }
    public enum RegressionStatus { PASS, PASS_WITH_WARNINGS, FAIL_FUNCTIONAL, FAIL_IDEMPOTENCE,
        FAIL_COMPILE, FAIL_FALSE_POSITIVE, FAIL_PERFORMANCE, FAIL_LICENSE, INCONCLUSIVE }
    public enum Risk { LOW, MEDIUM, HIGH, CRITICAL }

    public record Artifact(String groupId, String artifactId, String version, String repository,
                           String sha256, String pomSha256, LicenseType license,
                           boolean signatureVerified, String sbomRef, List<Artifact> dependencies) {
        public Artifact {
            require(groupId, "groupId"); require(artifactId, "artifactId"); require(version, "version");
            require(repository, "repository"); requireDigest(sha256, "sha256"); requireDigest(pomSha256, "pomSha256");
            license = license == null ? LicenseType.UNKNOWN : license;
            dependencies = dependencies == null ? List.of() : List.copyOf(dependencies);
        }
        public String coordinate() { return groupId + ":" + artifactId + ":" + version; }
    }

    public record QualityProfile(double historicalCompletionRate, boolean idempotent,
                                 boolean regressionVerified, int patchPrecision,
                                 boolean typeAttributionComplete, int runtimePerformance,
                                 int maintainerConfidence) {
        public QualityProfile {
            if (historicalCompletionRate < 0 || historicalCompletionRate > 1 || patchPrecision < 0 || patchPrecision > 100
                    || runtimePerformance < 0 || runtimePerformance > 100 || maintainerConfidence < 0 || maintainerConfidence > 100)
                throw new IllegalArgumentException("recipe quality is outside policy");
        }
    }

    public record Descriptor(String recipeName, String displayName, Artifact artifact,
                             Set<String> capabilities, Set<String> supportedSources,
                             Set<String> supportedTargets, Map<String,String> optionTypes,
                             List<String> childRecipes, PromotionStatus promotionStatus,
                             QualityProfile quality, boolean descriptorValid,
                             Set<String> conflictingRecipes) {
        public Descriptor {
            require(recipeName, "recipeName"); require(displayName, "displayName");
            if (artifact == null || promotionStatus == null || quality == null) throw new IllegalArgumentException("recipe descriptor is incomplete");
            capabilities = Set.copyOf(capabilities); supportedSources = Set.copyOf(supportedSources);
            supportedTargets = Set.copyOf(supportedTargets); optionTypes = Map.copyOf(optionTypes);
            childRecipes = List.copyOf(childRecipes); conflictingRecipes = Set.copyOf(conflictingRecipes);
        }
    }

    public record Catalog(String version, Map<String,Descriptor> descriptors) {
        public Catalog { require(version, "catalogVersion"); descriptors = Map.copyOf(descriptors); }
    }

    public record CommercialGrant(String grantId, Set<ExecutionContext> contexts, Set<String> artifactCoordinates,
                                  Instant validFrom, Instant validUntil, String documentHash, String approvedBy) {
        public CommercialGrant {
            require(grantId, "grantId"); contexts = Set.copyOf(contexts); artifactCoordinates = Set.copyOf(artifactCoordinates);
            if (validFrom == null || validUntil == null || !validUntil.isAfter(validFrom)) throw new IllegalArgumentException("commercial grant window is invalid");
            requireDigest(documentHash, "documentHash"); require(approvedBy, "approvedBy");
        }
        public boolean permits(Artifact artifact, ExecutionContext context, Instant at) {
            return contexts.contains(context) && artifactCoordinates.contains(artifact.coordinate())
                    && !at.isBefore(validFrom) && at.isBefore(validUntil);
        }
    }

    public record LicenseDecision(String decisionId, String recipeName, ExecutionContext executionContext,
                                  LicenseType effectiveLicense, LicenseOutcome decision, String reasonCode,
                                  String policyVersion, Instant evaluatedAt, List<String> evidenceRefs) {
        public LicenseDecision {
            require(decisionId, "decisionId"); require(recipeName, "recipeName"); require(reasonCode, "reasonCode");
            require(policyVersion, "policyVersion"); evidenceRefs = List.copyOf(evidenceRefs);
        }
        public boolean permitsExecution() { return decision == LicenseOutcome.ALLOWED
                || decision == LicenseOutcome.ALLOWED_WITH_ATTRIBUTION
                || decision == LicenseOutcome.ALLOWED_WITH_COMMERCIAL_GRANT; }
    }

    public record SelectionRequest(String migrationStepId, Set<String> requiredCapabilities,
                                   String sourceVersion, String targetVersion,
                                   ExecutionContext executionContext, String licensePolicyVersion,
                                   Instant evaluatedAt) {
        public SelectionRequest {
            require(migrationStepId, "migrationStepId"); requiredCapabilities = Set.copyOf(requiredCapabilities);
            if (requiredCapabilities.isEmpty()) throw new IllegalArgumentException("required capabilities are empty");
            require(sourceVersion, "sourceVersion"); require(targetVersion, "targetVersion");
            require(licensePolicyVersion, "licensePolicyVersion");
            if (executionContext == null || evaluatedAt == null) throw new IllegalArgumentException("selection context is incomplete");
        }
    }

    public record Candidate(String recipeName, int score, Set<String> capabilityCoverage,
                            List<String> rejectionReasons, LicenseDecision licenseDecision, boolean selected) {
        public Candidate {
            capabilityCoverage = Set.copyOf(capabilityCoverage); rejectionReasons = List.copyOf(rejectionReasons);
            if (score < 0 || score > 100) throw new IllegalArgumentException("candidate score is outside policy");
        }
    }

    public record Selection(String schemaVersion, String selectionId, String migrationStepId,
                            String catalogVersion, Set<String> requiredCapabilities,
                            List<Candidate> candidates, List<String> selectedRecipes,
                            SelectionStatus status, List<String> findings) {
        public Selection {
            requireSchema(schemaVersion); requiredCapabilities = Set.copyOf(requiredCapabilities);
            candidates = List.copyOf(candidates); selectedRecipes = List.copyOf(selectedRecipes); findings = List.copyOf(findings);
        }
    }

    public record ResolvedRecipe(String recipeName, Artifact artifact, Map<String,Object> options,
                                 int executionOrder, String licenseDecisionId) {
        public ResolvedRecipe {
            require(recipeName, "recipeName"); options = Map.copyOf(options); require(licenseDecisionId, "licenseDecisionId");
            if (artifact == null || executionOrder < 0) throw new IllegalArgumentException("resolved recipe is invalid");
        }
    }

    public record RuntimeConfiguration(String jdkVersion, String mavenVersion, String sandboxImageDigest,
                                       String networkPolicyId, int memoryMb, int cpuLimit) {
        public RuntimeConfiguration {
            require(jdkVersion, "jdkVersion"); require(mavenVersion, "mavenVersion");
            requireDigest(sandboxImageDigest, "sandboxImageDigest"); require(networkPolicyId, "networkPolicyId");
            if (memoryMb < 512 || cpuLimit < 1) throw new IllegalArgumentException("runtime resources are invalid");
        }
    }

    public record ExecutionManifest(String schemaVersion, String manifestId, String sourceSnapshotId,
                                    String migrationStepId, String sourceCommit, String targetProfileId,
                                    String compatibilitySnapshotId, String rewriteBomVersion,
                                    String rewriteMavenPluginVersion, List<ResolvedRecipe> recipes,
                                    RuntimeConfiguration runtime, int maxCycles, int timeoutSeconds,
                                    boolean exportDataTables, List<String> licenseDecisionIds,
                                    String policyHash, Instant createdAt, String manifestHash) {
        public ExecutionManifest {
            requireSchema(schemaVersion); recipes = List.copyOf(recipes); licenseDecisionIds = List.copyOf(licenseDecisionIds);
            if (recipes.isEmpty() || runtime == null || maxCycles < 1 || maxCycles > 10 || timeoutSeconds < 1 || timeoutSeconds > 14400)
                throw new IllegalArgumentException("execution manifest is outside policy");
            if (!exportDataTables) throw new IllegalArgumentException("execution manifest must export OpenRewrite data tables");
            requireDigest(policyHash, "policyHash"); requireRawDigest(manifestHash, "manifestHash");
        }
    }

    public record FileResult(String beforePath, String afterPath, String parentRecipe,
                             String actualRecipe, int cycle, int changedLines, String module,
                             String semanticIntent, Risk risk, boolean deleted, boolean binary) {
        public FileResult {
            require(beforePath, "beforePath"); require(afterPath, "afterPath"); require(actualRecipe, "actualRecipe");
            require(module, "module"); require(semanticIntent, "semanticIntent");
            if (cycle < 1 || changedLines < 0 || risk == null) throw new IllegalArgumentException("file result is invalid");
        }
    }

    public record RunEvidence(String manifestHash, int cycleCount, List<FileResult> fileResults,
                              List<String> parseErrors, List<String> recipeErrors,
                              Set<String> dataTables, List<String> treeHashes,
                              boolean secondRunChanged, boolean timedOut, boolean resourceExceeded,
                              boolean workspaceBoundaryViolation, Map<String,Long> resourceUsage) {
        public RunEvidence {
            requireRawDigest(manifestHash, "manifestHash"); fileResults = List.copyOf(fileResults);
            parseErrors = List.copyOf(parseErrors); recipeErrors = List.copyOf(recipeErrors);
            dataTables = Set.copyOf(dataTables); treeHashes = List.copyOf(treeHashes); resourceUsage = Map.copyOf(resourceUsage);
        }
    }

    public record IdempotenceResult(IdempotenceStatus status, List<String> treeHashes,
                                    int secondRunChangedFiles, String reasonCode) {
        public IdempotenceResult { treeHashes = List.copyOf(treeHashes); require(reasonCode, "reasonCode"); }
    }

    public record RecipeRun(String schemaVersion, String runId, String manifestId, String manifestHash,
                            RunStatus status, int cycleCount, int changedFileCount, int parseFailureCount,
                            int recipeErrorCount, IdempotenceResult idempotence, List<String> findings,
                            List<String> evidenceRefs) {
        public RecipeRun { requireSchema(schemaVersion); findings = List.copyOf(findings); evidenceRefs = List.copyOf(evidenceRefs); }
    }

    public record PatchPolicy(int maximumFilesPerSegment, int maximumChangedLinesPerSegment,
                              Set<String> allowedPathPrefixes, Set<String> manualReviewIntents) {
        public PatchPolicy {
            if (maximumFilesPerSegment < 1 || maximumChangedLinesPerSegment < 1) throw new IllegalArgumentException("patch thresholds are invalid");
            allowedPathPrefixes = Set.copyOf(allowedPathPrefixes); manualReviewIntents = Set.copyOf(manualReviewIntents);
        }
    }

    public record PatchSegment(String schemaVersion, String segmentId, String migrationStepId,
                               String primaryIntent, List<String> recipeNames, List<String> modules,
                               List<String> files, Risk risk, List<String> requiredValidations,
                               boolean manualReviewRequired, String patchArtifactRef, List<String> findings) {
        public PatchSegment {
            requireSchema(schemaVersion); recipeNames = List.copyOf(recipeNames); modules = List.copyOf(modules);
            files = List.copyOf(files); requiredValidations = List.copyOf(requiredValidations); findings = List.copyOf(findings);
        }
    }

    public record RegressionEvidence(boolean descriptorPassed, boolean unitTestsPassed,
                                     boolean negativeTestsPassed, boolean compilePassed,
                                     IdempotenceStatus idempotence, boolean compositionPassed,
                                     boolean performanceWithinBudget, boolean licenseAllowed,
                                     boolean artifactSigned, boolean sbomPresent,
                                     int humanReviewers, boolean rollbackDefined) {}

    public record PromotionDecision(RegressionStatus regressionStatus, PromotionStatus promotionStatus,
                                    boolean productionEligible, List<String> blockingReasons) {
        public PromotionDecision { blockingReasons = List.copyOf(blockingReasons); }
    }

    static void require(String value, String field) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(field + " is required");
    }
    static void requireSchema(String value) { if (!"1.0".equals(value)) throw new IllegalArgumentException("unsupported schema version"); }
    static void requireDigest(String value, String field) {
        if (value == null || !value.matches("sha256:[0-9a-f]{64}")) throw new IllegalArgumentException(field + " must be a sha256 digest");
    }
    static void requireRawDigest(String value, String field) {
        if (value == null || !value.matches("[0-9a-f]{64}")) throw new IllegalArgumentException(field + " must be a raw sha256 digest");
    }
}
