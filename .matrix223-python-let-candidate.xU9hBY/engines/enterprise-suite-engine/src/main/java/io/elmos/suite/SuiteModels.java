package io.elmos.suite;

import java.util.Objects;
import java.util.Set;

public final class SuiteModels {
    private SuiteModels() {}

    public enum AdapterStatus { NOT_CONFIGURED, READY, LICENSE_BLOCKED }
    public enum RunnerType { DISCOVERY, SAP, ORACLE, DYNAMICS, SALESFORCE, MASTER_DATA,
        DATA_MIGRATION, PROCESS_VALIDATION, INTEGRATION_TEST, CUTOVER }
    public enum SuitePlatform { SAP_ECC, SAP_S4HANA, ORACLE_EBS, ORACLE_FUSION,
        DYNAMICS_365, DATAVERSE, POWER_PLATFORM, SALESFORCE, OTHER }
    public enum UsageStatus { ACTIVE, SEASONAL, DORMANT, HISTORICAL, UNKNOWN }
    public enum CleanCoreStatus { CLEAN, CLEAN_WITH_APPROVED_EXTENSION, UPGRADE_STABLE,
        UPGRADE_AT_RISK, CORE_MODIFIED, UNSUPPORTED, UNKNOWN }
    public enum TargetProfile { KEEP_AND_GOVERN, TECHNICAL_UPGRADE, SYSTEM_CONVERSION,
        GREENFIELD_IMPLEMENTATION, SELECTIVE_DATA_TRANSITION, CLOUD_REIMPLEMENTATION,
        MODULE_REPLACEMENT, COMPOSABLE_SUITE, DUAL_SUITE_COEXISTENCE, FULL_REPLACEMENT, RETIRE }
    public enum MigrationState { SUITE_DISCOVERY, PROCESS_BASELINING, CUSTOMIZATION_CLASSIFYING,
        MASTER_DATA_PROFILING, TARGET_PLANNING, STANDARD_PROCESS_DESIGNING, EXTENSION_DECOUPLING,
        TARGET_CONFIGURING, DATA_MIGRATING, PROCESS_VALIDATING, PARALLEL_RUNNING,
        ORGANIZATION_CUTOVER, STABILITY_HOLD, LEGACY_READ_ONLY, ARCHIVING, DECOMMISSIONED }
    public enum EquivalenceStatus { EXACT, BUSINESS_EQUIVALENT, STANDARDIZED_APPROVED,
        EXPECTED_DIFFERENCE, REGRESSION, INCONCLUSIVE }

    public record Adapter(String id, String product, String version, AdapterStatus status,
                          Set<RunnerType> runnerTypes, Set<String> permissions,
                          String networkPolicy, boolean productionCapable) {
        public Adapter {
            require(id, "id"); require(product, "product"); require(version, "version");
            Objects.requireNonNull(status); runnerTypes = Set.copyOf(runnerTypes);
            permissions = Set.copyOf(permissions); require(networkPolicy, "networkPolicy");
            if (!"ALLOWLIST_REQUIRED".equals(networkPolicy)) throw new IllegalArgumentException("suite egress must be allowlisted");
            if (permissions.stream().anyMatch(SuiteModels::prohibited)) throw new IllegalArgumentException("prohibited suite adapter permission");
        }
    }

    static void require(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required");
    }

    private static boolean prohibited(String permission) {
        return Set.of("MODIFY_PRODUCTION_CONFIGURATION", "PUBLISH_PRODUCTION_TRANSPORT",
                "DEPLOY_PRODUCTION_SOLUTION", "DEPLOY_SALESFORCE_PRODUCTION",
                "MODIFY_USER_PERMISSION", "BULK_DELETE_BUSINESS_DATA",
                "ACCEPT_PROCESS_DIFFERENCE", "SWITCH_MASTER_DATA_AUTHORITY",
                "AUTO_CUTOVER", "AUTO_DECOMMISSION").contains(permission);
    }
}
