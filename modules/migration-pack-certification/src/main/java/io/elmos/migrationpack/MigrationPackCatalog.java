package io.elmos.migrationpack;

import java.util.List;

import static io.elmos.migrationpack.MigrationPackModels.*;

/** Exact package metadata; product Batch numbers are deliberately not used here. */
public final class MigrationPackCatalog {
    private MigrationPackCatalog() {}

    private static final List<String> COMMON = List.of(
            "EXACT_DIRECTION_AND_VERSION_REQUIRED", "IMMUTABLE_SOURCE_AND_TARGET_SNAPSHOTS",
            "INDEPENDENT_HOLDOUT_EVIDENCE", "UNSUPPORTED_SEMANTICS_REMAIN_EXPLICIT",
            "NO_WEAKENED_TEST_SECURITY_OR_TYPES", "NO_PRODUCTION_MUTATION_FROM_ADMISSION");

    public static List<PackDefinition> all() {
        return List.of(
                definition(29, "directed-language-route", "scripts/batch29/run_route_gate.py", 20, 3,
                        List.of("DISCOVERY", "TYPED_IR", "SOURCE_BUILD", "TARGET_BUILD", "SEMANTIC_HOLDOUT", "SECURITY"),
                        List.of("support-matrix", "route-manifest", "route-certification")),
                definition(30, "framework-modernization", "scripts/batch30/run_framework_gate.py", 20, 4,
                        List.of("DISCOVERY", "FCM", "SOURCE_BUILD", "TARGET_BUILD", "STARTUP", "BEHAVIOR_HOLDOUT", "SECURITY"),
                        List.of("framework-support-matrix", "framework-pack", "target-profile", "framework-certification")),
                definition(31, "database-and-data-platform", "scripts/batch31/run_database_gate.py", 22, 6,
                        List.of("DISCOVERY", "CANONICAL_DB_IR", "SOURCE_ENGINE", "TARGET_ENGINE", "DETAIL_RECONCILIATION", "WORKLOAD_HOLDOUT", "DATA_SAFETY"),
                        List.of("database-support-matrix", "database-pack", "workload-fingerprint", "canonical-db-ir", "data-migration-plan", "database-certification")),
                definition(32, "frontend-and-client", "scripts/batch32/run_client_gate.py", 20, 7,
                        List.of("DISCOVERY", "UI_INTERACTION_IR", "SOURCE_BUILD", "TARGET_BUILD", "BROWSER_DEVICE", "ACCESSIBILITY_VISUAL", "JOURNEY_HOLDOUT"),
                        List.of("client-support-matrix", "client-pack", "source-fingerprint", "target-profile", "ui-interaction-ir", "acceptance-profile", "client-certification")),
                definition(33, "cloud-iac-devops", "scripts/batch33/run_cloud_gate.py", 20, 8,
                        List.of("DISCOVERY", "RUNTIME_ARCHITECTURE_CONTRACT", "IAC_IR", "SOURCE_PLAN", "TARGET_PLAN", "ISOLATED_RUNTIME", "ROLLBACK_DESTROY", "SECURITY"),
                        List.of("cloud-support-matrix", "cloud-pack", "source-fingerprint", "target-profile", "runtime-architecture-contract", "iac-ir", "validation-profile", "cloud-certification")),
                definition(34, "portfolio-scale", "scripts/batch34/run_portfolio_gate.py", 22, 10,
                        List.of("INVENTORY", "DEPENDENCY_GRAPH", "WORK_UNITS", "CAMPAIGN", "SCALE_BENCHMARK", "FAIRNESS", "DR_REPLAY", "TENANT_SECURITY"),
                        List.of("portfolio-support-matrix", "portfolio-pack", "portfolio-inventory", "dependency-graph", "work-unit-plan", "scale-profile", "campaign-plan", "benchmark-result", "dr-replay-plan", "portfolio-certification")));
    }

    public static PackDefinition require(int pack) {
        return all().stream().filter(value -> value.pack() == pack).findFirst()
                .orElseThrow(() -> new IllegalArgumentException("unknown migration pack: M" + pack));
    }

    private static PackDefinition definition(int pack, String domain, String command, int skills, int schemas,
                                             List<String> phases, List<String> artifacts) {
        return new PackDefinition(pack, domain, "migration-pack-M" + pack + "-v1", command,
                skills, schemas, phases, artifacts, COMMON);
    }
}
