package io.elmos.testquality;

import java.time.Instant;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class QualityModels {
    private QualityModels() {}

    public enum TestType { UNIT, COMPONENT, INTEGRATION, CONTRACT, PROPERTY, MUTATION, E2E, VISUAL, ACCESSIBILITY, DATA, MODEL, PERFORMANCE, RESILIENCE }
    public enum RunnerType { UNIT, INTEGRATION, BROWSER_CLIENT, DATA_ML, PERFORMANCE, MUTATION }
    public enum AdapterStatus { NOT_CONFIGURED, READY, LICENSE_BLOCKED }
    public enum ExternalStatus { PASS, PASS_WITH_WARNINGS, CONDITIONAL_PASS, FAIL, NOT_RUN, INCONCLUSIVE, STALE }
    public enum GateStatus { PASS, PASS_WITH_WARNINGS, CONDITIONAL_PASS, FAIL, NOT_RUN, INCONCLUSIVE, STALE }
    public enum Confidence { HIGH, MODERATE, LOW, INSUFFICIENT, UNKNOWN }
    public enum AiStatus { GENERATED, COMPILABLE, EXECUTABLE, EFFECTIVE, REVIEW_REQUIRED, APPROVED, REJECTED, PROMOTED, REVOKED }
    public enum MigrationState {
        TEST_DISCOVERY, TEST_BASELINING, QUALITY_RISK_MODELING, TEST_PORTFOLIO_PLANNING,
        CHARACTERIZATION_BUILDING, TEST_MODERNIZING, ENVIRONMENT_PREPARING, TEST_EXECUTING,
        FLAKY_ANALYZING, TEST_EFFECTIVENESS_ANALYZING, QUALITY_GATE_EVALUATING, CONTINUOUS_VALIDATION
    }
    public enum ExceptionState {
        TEST_DISCOVERY_INCOMPLETE, TEST_BASELINE_UNSTABLE, TEST_COUNT_REGRESSION,
        TEST_ENVIRONMENT_UNAVAILABLE, TEST_DATA_INVALID, TEST_COVERAGE_INSUFFICIENT,
        CONTRACT_VERIFICATION_FAILED, PROPERTY_VIOLATED, MUTATION_SCORE_REGRESSION,
        FLAKY_RATE_EXCEEDED, QUALITY_RISK_UNCOVERED, QUALITY_GATE_FAILED, QUALITY_EVIDENCE_STALE
    }
    public enum EvidenceType {
        TEST_ESTATE, TEST_DISCOVERY, TEST_HEALTH, QUALITY_RISK_MODEL, QUALITY_COVERAGE,
        TEST_PORTFOLIO, CHARACTERIZATION_RESULT, GOLDEN_MASTER, CONTRACT_VERIFICATION,
        PROPERTY_TEST_RESULT, MUTATION_RESULT, TEST_DATA_RESULT, ENVIRONMENT_RESULT,
        AI_TEST_RESULT, FLAKY_RESULT, TEST_SELECTION, QUALITY_GATE, RELEASE_CONFIDENCE,
        CONTINUOUS_VALIDATION, DEFECT_LEARNING
    }
    public enum CostUnit {
        TEST_DISCOVERY_UNIT, UNIT_TEST_MINUTE, INTEGRATION_ENVIRONMENT_HOUR,
        CONTRACT_VERIFICATION, PROPERTY_EXAMPLE, MUTANT_EXECUTION, BROWSER_MINUTE,
        DEVICE_MINUTE, TEST_DATA_GENERATION, AI_TEST_GENERATION, PERFORMANCE_RUN,
        CONTINUOUS_VALIDATION_RUN
    }

    public record ToolAdapter(String adapterId, String framework, String version, AdapterStatus status,
                              Set<TestType> testTypes, Set<RunnerType> runnerTypes,
                              Set<String> permissions, boolean retrySupported,
                              boolean parallelSupported, boolean filteringSupported,
                              String reportFormat, String license, String defaultNetwork) {
        public ToolAdapter {
            require(adapterId, "adapterId"); require(framework, "framework"); require(version, "version");
            Objects.requireNonNull(status); testTypes = Set.copyOf(testTypes); runnerTypes = Set.copyOf(runnerTypes);
            permissions = Set.copyOf(permissions); require(reportFormat, "reportFormat"); require(license, "license");
            require(defaultNetwork, "defaultNetwork");
            if (!"DENY".equals(defaultNetwork)) throw new IllegalArgumentException("test adapter network must default deny");
            if (permissions.stream().anyMatch(QualityModels::prohibited)) throw new IllegalArgumentException("prohibited test adapter permission");
        }
    }

    public record PromotionRequest(String candidateId, String humanReviewer, boolean compilePassed,
                                   boolean runPassed, boolean failBeforeFixPassed, boolean repeatable,
                                   boolean mutationEffective, boolean isolationPassed) {}
    public record PromotionDecision(String candidateId, AiStatus status, boolean promoted,
                                    List<String> reasonCodes, Instant decidedAt) {}

    static void require(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required");
    }

    private static boolean prohibited(String permission) {
        String normalized = permission.toUpperCase(Locale.ROOT);
        return normalized.contains("MODIFY_GATE") || normalized.contains("AUTO_PROMOTE")
                || normalized.contains("PRODUCTION_SECRET") || normalized.contains("DELETE_TEST")
                || normalized.contains("AUTO_APPROVE_SNAPSHOT") || normalized.contains("HIDE_FAILURE");
    }
}
