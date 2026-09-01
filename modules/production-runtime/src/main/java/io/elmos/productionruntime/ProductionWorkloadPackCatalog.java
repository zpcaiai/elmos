package io.elmos.productionruntime;

import java.util.List;
import java.util.Map;
import java.util.Objects;

import io.elmos.productionruntime.ProductionRuntimeModels.OutputVerificationReceipt;

/**
 * Runtime-owned binding of the four package workload packs.
 *
 * <p>The source package remains declarative input.  This allow-list is the
 * executable boundary: an unknown job type or stage is rejected instead of
 * being silently routed through a generic implementation.</p>
 */
public final class ProductionWorkloadPackCatalog {
    private static final Map<String, WorkloadPackDefinition> BY_JOB_TYPE = Map.of(
            "SPRING_MODERNIZATION", pack("spring-modernization-v1", "SPRING_MODERNIZATION", List.of(
                    "inventory", "build-and-semantic-graph", "migration-plan", "dependency-upgrade", "jakarta-namespace",
                    "configuration", "web-layer", "service-transaction", "persistence", "security", "sql-integration",
                    "compile", "unit-integration-test", "behavioral-diff", "auto-repair", "regression-retest", "package-report"),
                    checks(
                            passed("target_build_pass"),
                            passed("behavior_diff_pass"),
                            zero("unresolved_p0_defects"))),
            "LANGUAGE_CONVERSION", pack("repository-language-conversion-v1", "LANGUAGE_CONVERSION", List.of(
                    "inventory", "semantic-ir", "compatibility-plan", "shared-types-schema", "leaf-symbol-conversion",
                    "module-conversion", "framework-adapters", "integration", "compile", "contract-test", "behavior-diff",
                    "auto-repair", "package-report"), checks(
                            passed("target_build_pass"),
                            passed("api_contract_preserved"),
                            passed("schema_contract_preserved"),
                            passed("behavior_diff_pass"),
                            zero("unresolved_p0_defects"))),
            "PROJECT_GENERATION", pack("multilingual-project-generation-v1", "PROJECT_GENERATION", List.of(
                    "requirements-normalization", "architecture-adr", "schema-api-contracts", "backend-generation",
                    "frontend-generation", "database-migrations", "integration", "test-generation", "build-test",
                    "security-quality-gates", "deployment-assets", "docs-report"), checks(
                            passed("target_build_pass"),
                            passed("target_test_pass"),
                            passed("security_gate_pass"),
                            passed("runnable_smoke_pass"),
                            zero("unresolved_p0_defects"))),
            "SQL_CONVERSION", pack("sql-dialect-routine-conversion-v1", "SQL_CONVERSION", List.of(
                    "inventory-parse", "dependency-graph", "dialect-gap-analysis", "ddl-conversion", "query-view-conversion",
                    "routine-conversion", "trigger-conversion", "target-compile", "result-regression", "performance-risk",
                    "auto-repair", "report-review"), checks(
                            passed("target_compile_pass"),
                            passed("result_regression_pass"),
                            passed("constraint_semantics_preserved"),
                            passed("transaction_semantics_preserved"),
                            zero("unresolved_semantic_gaps")))
    );

    private ProductionWorkloadPackCatalog() {}

    public static WorkloadPackDefinition require(String jobType, List<String> requestedStages) {
        WorkloadPackDefinition pack = BY_JOB_TYPE.get(jobType);
        if (pack == null) throw new ProductionRuntimeException("UNSUPPORTED_WORKLOAD_PACK", "job type is not bound to a production workload pack: " + jobType);
        Objects.requireNonNull(requestedStages, "requestedStages");
        int previous = -1;
        for (String stage : requestedStages) {
            int index = pack.stages().indexOf(stage);
            if (index < 0 || index <= previous) throw new ProductionRuntimeException("UNSUPPORTED_WORKLOAD_STAGE", "stage is not an ordered stage in " + pack.id() + ": " + stage);
            previous = index;
        }
        return pack;
    }

    /**
     * Require the full ordered stage contract declared by the package.  A
     * partial stage list remains supported for controlled sub-runs, but it
     * must be explicit at the API boundary rather than being mistaken for a
     * complete workload implementation.
     */
    public static WorkloadPackDefinition requireComplete(String jobType) {
        WorkloadPackDefinition pack = BY_JOB_TYPE.get(jobType);
        if (pack == null) {
            throw new ProductionRuntimeException(
                    "UNSUPPORTED_WORKLOAD_PACK",
                    "job type is not bound to a production workload pack: " + jobType);
        }
        return pack;
    }

    public static List<WorkloadPackDefinition> all() { return List.copyOf(BY_JOB_TYPE.values()); }

    public static void verifyOutput(
            String expectedJobType,
            String expectedWorkType,
            OutputVerificationReceipt receipt
    ) {
        Objects.requireNonNull(receipt, "output verification receipt");
        WorkloadPackDefinition pack = BY_JOB_TYPE.get(expectedJobType);
        if (pack == null) {
            throw new ProductionRuntimeException(
                    "UNSUPPORTED_WORKLOAD_PACK",
                    "job type is not bound to a production workload pack: " + expectedJobType);
        }
        if (!pack.id().equals(receipt.packId())
                || !expectedJobType.equals(receipt.jobType())
                || !expectedWorkType.equals(receipt.workType())) {
            throw new ProductionRuntimeException(
                    "OUTPUT_VERIFICATION_IDENTITY_MISMATCH",
                    "output verification does not match the durable workload identity");
        }
        for (CompletionCheck gate : pack.completionGates()) {
            Object actual = receipt.checks().get(gate.name());
            if (!gate.expected().matches(actual)) {
                throw new ProductionRuntimeException(
                        "OUTPUT_VERIFICATION_GATE_FAILED",
                        "required output gate did not pass: " + gate.name());
            }
        }
    }

    private static WorkloadPackDefinition pack(
            String id,
            String jobType,
            List<String> stages,
            List<CompletionCheck> gates
    ) {
        if (gates.isEmpty()) {
            throw new IllegalArgumentException("production workload packs require completion gates");
        }
        return new WorkloadPackDefinition(id, jobType, List.copyOf(stages), List.copyOf(gates));
    }

    private static List<CompletionCheck> checks(CompletionCheck... checks) {
        return List.of(checks);
    }

    private static CompletionCheck passed(String name) {
        return new CompletionCheck(name, ExpectedCheckValue.TRUE);
    }

    private static CompletionCheck zero(String name) {
        return new CompletionCheck(name, ExpectedCheckValue.ZERO);
    }

    public record WorkloadPackDefinition(
            String id,
            String jobType,
            List<String> stages,
            List<CompletionCheck> completionGates
    ) {}

    public record CompletionCheck(String name, ExpectedCheckValue expected) {
        public CompletionCheck {
            Objects.requireNonNull(name, "name");
            Objects.requireNonNull(expected, "expected");
        }
    }

    public enum ExpectedCheckValue {
        TRUE {
            @Override boolean matches(Object value) { return Boolean.TRUE.equals(value); }
        },
        ZERO {
            @Override boolean matches(Object value) {
                if (value instanceof Byte || value instanceof Short
                        || value instanceof Integer || value instanceof Long) {
                    return ((Number) value).longValue() == 0L;
                }
                return value instanceof java.math.BigInteger integer
                        && java.math.BigInteger.ZERO.equals(integer);
            }
        };

        abstract boolean matches(Object value);
    }
}
