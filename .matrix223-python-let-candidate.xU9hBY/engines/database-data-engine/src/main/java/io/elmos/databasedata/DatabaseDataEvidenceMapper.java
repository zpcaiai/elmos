package io.elmos.databasedata;

import java.util.List;
import java.util.Map;

import static io.elmos.databasedata.DatabaseDataModels.*;

public final class DatabaseDataEvidenceMapper {
    public record EvidenceExtension(
            String scope,
            String engine,
            String schema,
            EvidenceType evidenceType,
            String artifactRef,
            String risk,
            String check,
            CostUnit costUnit,
            List<String> relatedChangeRefs,
            Map<String, Object> providerExtension) {
        public EvidenceExtension {
            relatedChangeRefs = List.copyOf(relatedChangeRefs);
            providerExtension = Map.copyOf(providerExtension);
        }
    }

    public EvidenceExtension map(EvidenceType type, String artifactRef, List<String> changeRefs,
                                 Map<String, Object> providerExtension) {
        DatabaseDataModels.require(artifactRef, "artifactRef");
        return new EvidenceExtension("DATABASE_DATA_PLATFORM", "ELMOS_DATABASE_DATA",
                "elmos.database-data-evidence.v1", type, artifactRef, risk(type), check(type),
                cost(type), changeRefs, providerExtension);
    }

    private String risk(EvidenceType type) {
        return switch (type) {
            case SCHEMA_CONVERSION -> "DATA_COMPATIBILITY_RISK";
            case PROCEDURE_CONVERSION -> "BUSINESS_LOGIC_MIGRATION_RISK";
            case CDC_STATUS -> "DATA_SYNCHRONIZATION_RISK";
            case QUERY_PERFORMANCE -> "PERFORMANCE_RISK";
            case BI_VALIDATION, SEMANTIC_MODEL -> "BUSINESS_REPORTING_RISK";
            case DATA_GOVERNANCE -> "DATA_SECURITY_RISK";
            case DATABASE_CUTOVER -> "ROLLBACK_RISK";
            default -> "DATABASE_DATA_PLATFORM_RISK";
        };
    }

    private String check(EvidenceType type) {
        return switch (type) {
            case SCHEMA_CONVERSION, TARGET_SCHEMA -> "ELMOS / Schema Compatibility";
            case PROCEDURE_CONVERSION -> "ELMOS / Procedure Compatibility";
            case DATA_RECONCILIATION -> "ELMOS / Data Reconciliation";
            case QUERY_PERFORMANCE -> "ELMOS / Query Performance";
            case CDC_STATUS -> "ELMOS / CDC Readiness";
            case DATA_QUALITY -> "ELMOS / Data Quality";
            case SEMANTIC_MODEL, BI_VALIDATION -> "ELMOS / BI Metrics";
            case DATA_GOVERNANCE, DATA_LINEAGE -> "ELMOS / Governance";
            case DATABASE_CUTOVER -> "ELMOS / Database Cutover";
            default -> "ELMOS / Database Data Evidence";
        };
    }

    private CostUnit cost(EvidenceType type) {
        return switch (type) {
            case DATABASE_ESTATE, DATABASE_WORKLOAD -> CostUnit.DATABASE_DISCOVERY_UNIT;
            case SCHEMA_CONVERSION, TARGET_SCHEMA -> CostUnit.SCHEMA_OBJECT_CONVERSION;
            case PROCEDURE_CONVERSION -> CostUnit.PROCEDURE_CONVERSION;
            case QUERY_PERFORMANCE -> CostUnit.QUERY_VALIDATION;
            case BULK_LOAD -> CostUnit.BULK_LOAD_GB;
            case CDC_STATUS -> CostUnit.CDC_STREAM_HOUR;
            case DATA_QUALITY, DATA_RECONCILIATION -> CostUnit.DATA_QUALITY_RUN;
            case LAKEHOUSE_DESIGN, DATA_PRODUCT -> CostUnit.LAKEHOUSE_COMPUTE;
            case SEMANTIC_MODEL, BI_VALIDATION -> CostUnit.BI_ARTIFACT_MIGRATION;
            case DATA_LINEAGE, DATA_GOVERNANCE -> CostUnit.LINEAGE_EVENT;
            case DATABASE_CUTOVER, DATABASE_DECOMMISSION -> CostUnit.CUTOVER_OPERATION;
            default -> CostUnit.DATABASE_DISCOVERY_UNIT;
        };
    }
}
