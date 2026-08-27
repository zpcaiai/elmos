package io.elmos.productionruntime;

import java.util.List;
import java.util.Map;
import java.util.Objects;

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
                    Map.of("target_build_pass", true, "unresolved_p0_defects", 0)),
            "LANGUAGE_CONVERSION", pack("repository-language-conversion-v1", "LANGUAGE_CONVERSION", List.of(
                    "inventory", "semantic-ir", "compatibility-plan", "shared-types-schema", "leaf-symbol-conversion",
                    "module-conversion", "framework-adapters", "integration", "compile", "contract-test", "behavior-diff",
                    "auto-repair", "package-report"), Map.of("api_contract_preserved", true, "schema_contract_preserved", true)),
            "PROJECT_GENERATION", pack("multilingual-project-generation-v1", "PROJECT_GENERATION", List.of(
                    "requirements-normalization", "architecture-adr", "schema-api-contracts", "backend-generation",
                    "frontend-generation", "database-migrations", "integration", "test-generation", "build-test",
                    "security-quality-gates", "deployment-assets", "docs-report"), Map.of()),
            "SQL_CONVERSION", pack("sql-dialect-routine-conversion-v1", "SQL_CONVERSION", List.of(
                    "inventory-parse", "dependency-graph", "dialect-gap-analysis", "ddl-conversion", "query-view-conversion",
                    "routine-conversion", "trigger-conversion", "target-compile", "result-regression", "performance-risk",
                    "auto-repair", "report-review"), Map.of())
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

    public static List<WorkloadPackDefinition> all() { return List.copyOf(BY_JOB_TYPE.values()); }

    private static WorkloadPackDefinition pack(String id, String jobType, List<String> stages, Map<String, Object> gates) {
        return new WorkloadPackDefinition(id, jobType, List.copyOf(stages), Map.copyOf(gates));
    }

    public record WorkloadPackDefinition(String id, String jobType, List<String> stages, Map<String, Object> completionGates) {}
}
