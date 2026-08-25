package io.elmos.mainframe;

import java.time.Instant;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public final class MainframeModels {
    private MainframeModels() {}

    public enum AdapterStatus { NOT_CONFIGURED, READY, LICENSE_BLOCKED }
    public enum RunnerType { DISCOVERY, BUILD, TEST, DISTRIBUTED_ANALYSIS, PARALLEL_COMPARATOR, CUTOVER }
    public enum TargetProfile { KEEP_AND_OPTIMIZE, API_ENABLE, MODULARIZE_COBOL, HYBRID_EXTRACT,
        COBOL_TO_JAVA, REPLATFORM_RUNTIME, DATA_ONLY_MODERNIZATION, PACKAGE_REPLACEMENT, RETIRE }
    public enum Authority { MAINFRAME_AUTHORITATIVE, DUAL_WRITE_MAINFRAME_AUTH, DUAL_WRITE_NEW_AUTH,
        NEW_AUTHORITATIVE, MAINFRAME_READ_ONLY, DECOMMISSIONED }
    public enum MigrationState { ESTATE_DISCOVERY, SOURCE_AND_RUNTIME_CORRELATION, SEMANTIC_GRAPH_BUILDING,
        RULE_EXTRACTION, DOMAIN_SLICING, TARGET_PLANNING, BASELINE_BUILDING, INTERFACE_STABILIZING,
        REFACTORING_OR_TRANSFORMING, SEMANTIC_VALIDATING, PARALLEL_RUNNING, TRANSACTION_CUTOVER,
        BATCH_CUTOVER, STABILITY_HOLD, LEGACY_READ_ONLY, DECOMMISSION_READY, DECOMMISSIONED }
    public enum EquivalenceStatus { EXACT, BUSINESS_EQUIVALENT, EXPECTED_DIFFERENCE, REGRESSION, INCONCLUSIVE }
    public enum RuleEvidence { SOURCE_DIRECT, SOURCE_INFERRED, RUNTIME_OBSERVED, TEST_CONFIRMED, BUSINESS_APPROVED }

    public record Adapter(String id, String product, String version, AdapterStatus status,
                          Set<RunnerType> runnerTypes, Set<String> permissions,
                          String networkPolicy, boolean productionCapable) {
        public Adapter {
            require(id, "id"); require(product, "product"); require(version, "version");
            Objects.requireNonNull(status); runnerTypes = Set.copyOf(runnerTypes);
            permissions = Set.copyOf(permissions); require(networkPolicy, "networkPolicy");
            if (!"ALLOWLIST_REQUIRED".equals(networkPolicy)) throw new IllegalArgumentException("mainframe egress must be allowlisted");
            if (permissions.stream().anyMatch(MainframeModels::prohibited)) throw new IllegalArgumentException("prohibited mainframe adapter permission");
        }
    }

    public record RuleApprovalRequest(String ruleId, String businessOwner, RuleEvidence evidence,
                                      boolean sourceLinked, boolean runtimeLinked, boolean sideEffectsReviewed) {}
    public record RuleApprovalDecision(String ruleId, boolean authoritative, List<String> reasons, Instant decidedAt) {}

    static void require(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required");
    }

    private static boolean prohibited(String permission) {
        return Set.of("SUBMIT_ARBITRARY_JCL", "WRITE_PRODUCTION_DATASET", "WRITE_PRODUCTION_LOADLIB",
                "ALTER_CICS_RESOURCE", "ALTER_IMS_RESOURCE", "ALTER_DB2", "MODIFY_SCHEDULER").contains(permission);
    }
}
