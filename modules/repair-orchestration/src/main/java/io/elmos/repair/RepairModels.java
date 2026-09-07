package io.elmos.repair;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class RepairModels {
    private RepairModels() {}

    public enum Stage { DEPENDENCY_RESOLUTION, COMPILE, UNIT_TEST, INTEGRATION_TEST, PACKAGE, STATIC_ANALYSIS, UNKNOWN }
    public enum ErrorCategory { DEPENDENCY, COMPILATION, TYPE_MISMATCH, MISSING_SYMBOL, TEST_FAILURE,
        TEST_INFRASTRUCTURE, CONFIGURATION, SECURITY, TIMEOUT, RESOURCE, UNKNOWN }
    public enum Risk { LOW, MEDIUM, HIGH, CRITICAL }
    public enum ProviderType { CODEX, CLAUDE, OPENHANDS, HUMAN }
    public enum RoutingOutcome { ROUTED, HUMAN_REQUIRED, NO_ELIGIBLE_PROVIDER, BUDGET_BLOCKED }
    public enum BudgetStatus { RESERVED, REJECTED, SETTLED, UNKNOWN_USAGE_CHARGED }
    public enum LoopAction { RETRY_SAME_PROVIDER, SWITCH_PROVIDER, VALIDATE, ESCALATE_HUMAN, STOP_SUCCESS,
        STOP_BUDGET, STOP_OSCILLATION, STOP_NO_PROGRESS }

    public record RawFailure(String source, Stage stage, String module, int exitCode, String log,
                             Map<String,String> metadata) {
        public RawFailure {
            require(source, "source"); require(module, "module"); require(log, "log");
            stage = stage == null ? Stage.UNKNOWN : stage;
            metadata = metadata == null ? Map.of() : Map.copyOf(metadata);
        }
    }

    public record Failure(String failureId, Stage stage, ErrorCategory category, String module,
                          String symbol, String normalizedMessage, String fingerprint,
                          List<String> evidenceRefs, boolean retryable) {
        public Failure {
            require(failureId, "failureId"); require(module, "module"); require(normalizedMessage, "normalizedMessage");
            require(fingerprint, "fingerprint"); evidenceRefs = List.copyOf(evidenceRefs);
        }
    }

    public record FailureCluster(String clusterId, String fingerprint, String primaryFailureId,
                                 List<String> memberFailureIds, ErrorCategory category, Stage stage,
                                 String module) {
        public FailureCluster { memberFailureIds = List.copyOf(memberFailureIds); }
    }

    public record RepairScope(Set<String> allowedPathPrefixes, Set<String> deniedPathPrefixes,
                              Set<String> allowedCommands, int maximumFiles, int maximumChangedLines,
                              boolean allowTestChanges, boolean allowBuildConfigurationChanges) {
        public RepairScope {
            allowedPathPrefixes = Set.copyOf(allowedPathPrefixes); deniedPathPrefixes = Set.copyOf(deniedPathPrefixes);
            allowedCommands = Set.copyOf(allowedCommands);
            if (maximumFiles < 1 || maximumChangedLines < 1) throw new IllegalArgumentException("repair limits must be positive");
        }
    }

    public record ValidationRequirement(String validator, boolean independent, boolean blocking) {
        public ValidationRequirement { require(validator, "validator"); }
    }

    public record RepairTask(String schemaVersion, String taskId, String clusterId, String intent,
                             RepairScope scope, List<String> forbiddenActions,
                             List<ValidationRequirement> requiredValidations, Risk risk,
                             String contextHash, int maximumAttempts, Instant createdAt) {
        public RepairTask {
            schema(schemaVersion); require(taskId, "taskId"); require(clusterId, "clusterId"); require(intent, "intent");
            if (scope == null || risk == null || createdAt == null || maximumAttempts < 1 || maximumAttempts > 12)
                throw new IllegalArgumentException("repair task is incomplete");
            forbiddenActions = List.copyOf(forbiddenActions); requiredValidations = List.copyOf(requiredValidations);
        }
    }

    public record ContextItem(String kind, String reference, String contentHash, int bytes,
                              int priority, boolean secret, boolean repositoryControlled) {
        public ContextItem {
            require(kind, "kind"); require(reference, "reference"); digest(contentHash, "contentHash");
            if (bytes < 0 || priority < 0) throw new IllegalArgumentException("context item size or priority is invalid");
        }
    }

    public record ContextPack(String schemaVersion, String taskId, List<ContextItem> items,
                              int totalBytes, boolean truncated, boolean repositoryContentUntrusted,
                              String packHash) {
        public ContextPack {
            schema(schemaVersion); items = List.copyOf(items); digest(packHash, "packHash");
            if (totalBytes < 0) throw new IllegalArgumentException("context bytes are invalid");
        }
    }

    public record ProviderProfile(String providerId, ProviderType type, boolean enabled,
                                  Set<String> allowedResidencies, boolean supportsPrivateRepositories,
                                  Set<String> tools, Set<Risk> allowedRisks, int contextLimitBytes,
                                  long maximumCostMicrosPerTask, int priority) {
        public ProviderProfile {
            require(providerId, "providerId"); allowedResidencies = Set.copyOf(allowedResidencies);
            tools = Set.copyOf(tools); allowedRisks = Set.copyOf(allowedRisks);
            if (contextLimitBytes < 1 || maximumCostMicrosPerTask < 0 || priority < 0)
                throw new IllegalArgumentException("provider profile is invalid");
        }
    }

    public record RoutingRequest(RepairTask task, boolean privateRepository, String residency,
                                 Set<String> requiredTools, int contextBytes, long estimatedCostMicros,
                                 long remainingBudgetMicros) {
        public RoutingRequest {
            require(residency, "residency"); requiredTools = Set.copyOf(requiredTools);
            if (contextBytes < 0 || estimatedCostMicros < 0 || remainingBudgetMicros < 0)
                throw new IllegalArgumentException("routing request budget is invalid");
        }
    }

    public record RoutingDecision(String decisionId, RoutingOutcome outcome, String providerId,
                                  List<String> reasons, List<String> consideredProviderIds) {
        public RoutingDecision {
            require(decisionId, "decisionId"); reasons = List.copyOf(reasons); consideredProviderIds = List.copyOf(consideredProviderIds);
        }
    }

    public record RepairBudget(String budgetId, long maximumCostMicros, int maximumInputTokens,
                               int maximumOutputTokens, int maximumWallSeconds) {
        public RepairBudget {
            require(budgetId, "budgetId");
            if (maximumCostMicros < 0 || maximumInputTokens < 1 || maximumOutputTokens < 1 || maximumWallSeconds < 1)
                throw new IllegalArgumentException("repair budget is invalid");
        }
    }

    public record BudgetReservation(String reservationId, String budgetId, String taskId,
                                    long reservedCostMicros, int reservedInputTokens,
                                    int reservedOutputTokens, BudgetStatus status, String reason) {}

    public record Usage(long costMicros, int inputTokens, int outputTokens, int wallSeconds, boolean reported) {}

    public record AgentPatch(String taskId, int attempt, String providerId, String baseTreeHash,
                             String resultTreeHash, List<String> changedFiles, int changedLines,
                             List<String> requestedCommands, boolean testsChanged,
                             boolean buildConfigurationChanged, boolean filesDeleted,
                             String patchArtifactRef) {
        public AgentPatch {
            changedFiles = List.copyOf(changedFiles); requestedCommands = List.copyOf(requestedCommands);
            if (attempt < 1 || changedLines < 0) throw new IllegalArgumentException("agent patch is invalid");
        }
    }

    public record PatchReview(boolean allowed, boolean manualReviewRequired, List<String> findings,
                              List<String> independentValidations) {
        public PatchReview { findings = List.copyOf(findings); independentValidations = List.copyOf(independentValidations); }
    }

    public record VerificationResult(boolean buildPassed, boolean targetedTestsPassed,
                                     boolean regressionPassed, String failureFingerprint,
                                     int validationScore, List<String> evidenceRefs) {
        public VerificationResult { evidenceRefs = List.copyOf(evidenceRefs); }
        public boolean passed() { return buildPassed && targetedTestsPassed && regressionPassed && !evidenceRefs.isEmpty(); }
    }

    public record AttemptSnapshot(int attempt, String providerId, String beforeFingerprint,
                                  String afterFingerprint, String resultTreeHash, int validationScore,
                                  List<String> changedFiles) {
        public AttemptSnapshot { changedFiles = List.copyOf(changedFiles); }
    }

    public record LoopDecision(LoopAction action, String reasonCode, int nextAttempt,
                               String nextProviderId, List<String> evidenceRefs) {
        public LoopDecision { evidenceRefs = List.copyOf(evidenceRefs); }
    }

    public record ProviderCommandPlan(ProviderType provider, List<String> argv, Map<String,String> environment,
                                      Set<String> deniedCapabilities, boolean networkEnabled,
                                      boolean dockerSocketMounted) {
        public ProviderCommandPlan {
            argv = List.copyOf(argv); environment = Map.copyOf(environment); deniedCapabilities = Set.copyOf(deniedCapabilities);
        }
    }

    public record EscalationPackage(String escalationId, String taskId, String reasonCode,
                                    List<String> failureFingerprints, List<String> attemptedProviders,
                                    List<String> patchRefs, List<String> validationEvidenceRefs,
                                    long consumedCostMicros, List<String> requiredHumanDecisions) {
        public EscalationPackage {
            failureFingerprints = List.copyOf(failureFingerprints); attemptedProviders = List.copyOf(attemptedProviders);
            patchRefs = List.copyOf(patchRefs); validationEvidenceRefs = List.copyOf(validationEvidenceRefs);
            requiredHumanDecisions = List.copyOf(requiredHumanDecisions);
        }
    }

    static void require(String value, String field) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(field + " is required");
    }
    static void schema(String value) { if (!"1.0".equals(value)) throw new IllegalArgumentException("unsupported schema version"); }
    static void digest(String value, String field) {
        if (value == null || !value.matches("[0-9a-f]{64}")) throw new IllegalArgumentException(field + " must be a raw sha256 digest");
    }
}
