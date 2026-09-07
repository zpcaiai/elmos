package io.elmos.databasedata;

import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class DatabaseDataModels {
    private DatabaseDataModels() {}

    public enum DatabaseVendor { ORACLE, SQL_SERVER, MYSQL, POSTGRESQL, DATA_PLATFORM, BI_VALIDATION }
    public enum ModernizationTrack { OLTP_DATABASE, ANALYTICS_PLATFORM, BI_SEMANTIC }
    public enum RunnerStatus { NOT_CONFIGURED, READY }
    public enum Feasibility { FEASIBLE, FEASIBLE_WITH_ADAPTER, FEASIBLE_WITH_REDESIGN, PILOT_REQUIRED, BLOCKED, UNKNOWN }
    public enum Strategy {
        IN_PLACE_UPGRADE, SAME_ENGINE_REPLATFORM, MANAGED_SAME_ENGINE,
        HETEROGENEOUS_REPLATFORM, DATABASE_DECOMPOSITION, READ_SCALE_OFFLOAD,
        ANALYTICS_OFFLOAD, LAKEHOUSE_MODERNIZATION, ARCHIVE_ONLY
    }
    public enum MigrationState {
        DISCOVERY, WORKLOAD_BASELINING, TARGET_PLANNING, SCHEMA_CONVERTING,
        PROCEDURE_CONVERTING, TARGET_PROVISIONING, INITIAL_LOADING,
        CDC_SYNCHRONIZING, DUAL_RUNNING, RECONCILING, READ_CUTOVER,
        WRITE_CUTOVER, FULL_TARGET, STABILITY_HOLD, SOURCE_READ_ONLY,
        ARCHIVING, DECOMMISSIONED
    }
    public enum CutoverStatus {
        CUTOVER_READY, CUTOVER_READY_WITH_CONDITIONS, CUTOVER_BLOCKED,
        CUTOVER_IN_PROGRESS, CUTOVER_COMPLETED, ROLLBACK_REQUIRED
    }
    public enum ExceptionState {
        DATABASE_ESTATE_INCOMPLETE, TARGET_INCOMPATIBLE, SCHEMA_CONVERSION_BLOCKED,
        PROCEDURE_REDESIGN_REQUIRED, QUERY_PERFORMANCE_REGRESSION, INITIAL_LOAD_FAILED,
        CDC_UNSUPPORTED, CDC_LAG_EXCEEDED, DDL_REPLICATION_FAILED,
        DATA_RECONCILIATION_FAILED, WRITE_CONFLICT, BI_SEMANTIC_REGRESSION,
        CUTOVER_PAUSED, ROLLBACK_REQUIRED, DECOMMISSION_BLOCKED
    }
    public enum EvidenceType {
        DATABASE_ESTATE, DATABASE_WORKLOAD, CANONICAL_SCHEMA_IR, CANONICAL_SQL_IR,
        CANONICAL_PROCEDURE_IR, SQL_CONVERSION, PROCEDURE_CONVERSION, SCHEMA_CONVERSION,
        TARGET_SCHEMA, BULK_LOAD, CDC_STATUS, DATA_RECONCILIATION, QUERY_PERFORMANCE,
        DATA_QUALITY, LAKEHOUSE_DESIGN, DATA_PRODUCT, SEMANTIC_MODEL, BI_VALIDATION,
        DATA_LINEAGE, DATA_GOVERNANCE, DATABASE_CUTOVER, DATABASE_DECOMMISSION
    }
    public enum CostUnit {
        DATABASE_DISCOVERY_UNIT, SCHEMA_OBJECT_CONVERSION, PROCEDURE_CONVERSION,
        QUERY_VALIDATION, BULK_LOAD_GB, CDC_STREAM_HOUR, DATA_QUALITY_RUN,
        LAKEHOUSE_COMPUTE, BI_ARTIFACT_MIGRATION, LINEAGE_EVENT, CUTOVER_OPERATION
    }
    public enum QualityGate {
        PASS, PASS_WITH_BASELINE_DEFECTS, FAIL_MIGRATION_REGRESSION,
        HUMAN_REVIEW_REQUIRED, INCONCLUSIVE
    }
    public enum MappingCompatibility {
        LOSSLESS, LOSSLESS_WITH_CONSTRAINT, SEMANTICALLY_COMPATIBLE,
        LOSSY_APPROVED, REQUIRES_APPLICATION_CHANGE, UNSUPPORTED
    }

    public record RunnerProfile(
            DatabaseVendor vendor,
            List<String> tools,
            Set<String> discoveryPermissions,
            Set<String> productionCapabilities,
            boolean productionApprovalRequired,
            RunnerStatus status) {
        public RunnerProfile {
            Objects.requireNonNull(vendor, "vendor");
            tools = List.copyOf(tools);
            discoveryPermissions = Set.copyOf(discoveryPermissions);
            productionCapabilities = Set.copyOf(productionCapabilities);
            Objects.requireNonNull(status, "status");
            if (discoveryPermissions.stream().anyMatch(DatabaseDataModels::isWritePermission)) {
                throw new IllegalArgumentException("discovery profile must be read only");
            }
            if (!productionCapabilities.isEmpty() && !productionApprovalRequired) {
                throw new IllegalArgumentException("production database capability requires approval");
            }
        }
    }

    public record EstateProfile(
            String estateId,
            DatabaseVendor source,
            Set<String> requiredExtensions,
            boolean proceduresCritical,
            boolean analyticsContention,
            boolean residencyRestricted,
            boolean logBasedCdcAvailable,
            List<String> evidenceRefs) {
        public EstateProfile {
            require(estateId, "estateId");
            Objects.requireNonNull(source, "source");
            requiredExtensions = Set.copyOf(requiredExtensions);
            evidenceRefs = List.copyOf(evidenceRefs);
        }
    }

    public record TargetCandidate(
            Strategy strategy,
            ModernizationTrack track,
            DatabaseVendor source,
            String target,
            Feasibility feasibility,
            List<String> risks,
            List<String> requiredGates) {
        public TargetCandidate {
            Objects.requireNonNull(strategy); Objects.requireNonNull(track);
            Objects.requireNonNull(source); require(target, "target");
            Objects.requireNonNull(feasibility);
            risks = List.copyOf(risks);
            requiredGates = List.copyOf(requiredGates);
        }
    }

    public record CutoverEvidence(
            boolean initialLoadComplete,
            boolean snapshotFrontierConsistent,
            boolean cdcHealthy,
            boolean offsetRecoverable,
            boolean lagWithinThreshold,
            boolean reconciliationPassed,
            boolean queryResultsPassed,
            boolean queryPerformancePassed,
            boolean dataQualityPassed,
            boolean biMetricPassed,
            boolean biSecurityPassed,
            boolean governancePassed,
            boolean writerInventoryComplete,
            boolean ddlControlled,
            boolean rollbackPathValidated,
            boolean sourceWriteControlled,
            String approvedBy,
            List<String> evidenceRefs) {
        public CutoverEvidence {
            evidenceRefs = List.copyOf(Objects.requireNonNull(evidenceRefs, "evidenceRefs"));
        }
    }

    public record CutoverDecision(
            CutoverStatus status,
            boolean automatic,
            List<String> blockers,
            List<String> evidenceRefs,
            Map<String, String> gateResults) {
        public CutoverDecision {
            Objects.requireNonNull(status);
            blockers = List.copyOf(blockers);
            evidenceRefs = List.copyOf(evidenceRefs);
            gateResults = Map.copyOf(gateResults);
        }
    }

    private static boolean isWritePermission(String permission) {
        String normalized = permission.toUpperCase(java.util.Locale.ROOT);
        return normalized.contains("DDL") || normalized.contains("DML")
                || normalized.contains("ADMIN") || normalized.contains("WRITE");
    }

    static void require(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required");
    }
}
