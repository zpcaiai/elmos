package io.elmos.databasedata;

import org.junit.jupiter.api.Test;

import java.math.BigInteger;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static io.elmos.databasedata.DatabaseDataModels.QualityGate;
import static org.junit.jupiter.api.Assertions.assertEquals;

class Batch15AcceptanceScenariosTest {
    private final DatabaseModernizationPolicy policy = new DatabaseModernizationPolicy();

    @Test void scenario01_oracleEmptyStringIsExplicitSemanticRisk() {
        assertEquals("EMPTY_STRING_NULL_SEMANTIC_RISK", policy.oracleEmptyStringRisk(true));
    }

    @Test void scenario02_oracleNumberWithoutPrecisionRequiresProfile() {
        assertEquals("PROFILE_AND_USAGE_REQUIRED", policy.oracleNumberMapping(null, null));
    }

    @Test void scenario03_clusteredIndexIsRedesignedFromTargetWorkload() {
        assertEquals("REBUILD_FROM_TARGET_WORKLOAD", policy.clusteredIndexStrategy(true));
    }

    @Test void scenario04_sqlServerAgentJobRequiresCompleteInventory() {
        assertEquals("JOB_INVENTORY_INCOMPLETE", policy.schedulerJobDecision(true, true, true, false, true));
    }

    @Test void scenario05_mysqlUnsignedRangeCannotOverflowTarget() {
        assertEquals("NUMERIC_RANGE_RISK", policy.mysqlUnsignedMapping(
                new BigInteger("18446744073709551615"), BigInteger.valueOf(Long.MAX_VALUE)));
    }

    @Test void scenario06_productionSqlModeIsAuthoritative() {
        assertEquals("SQL_MODE_BEHAVIOR_DIFFERENCE", policy.sqlModeDecision("", "STRICT_ALL_TABLES"));
    }

    @Test void scenario07_requiredPostgresqlExtensionCanBlockManagedTarget() {
        assertEquals("TARGET_INCOMPATIBLE", policy.extensionCompatibility(
                Set.of("postgis", "customer_extension"), Set.of("postgis")));
    }

    @Test void scenario08_complexPlsqlPackageRequiresManualRedesign() {
        assertEquals("CRITICAL_MANUAL_REDESIGN", policy.procedureComplexity(true, true, true));
    }

    @Test void scenario09_triggerSideEffectsMustAllBeCovered() {
        assertEquals("TRIGGER_SIDE_EFFECT_UNRESOLVED", policy.triggerStrategy(
                Set.of("AUDIT_WRITE", "QUEUE_PUBLISH"), Set.of("AUDIT_WRITE")));
    }

    @Test void scenario10_dynamicTenantTableNameNeedsRuntimeEvidence() {
        assertEquals("RUNTIME_DEPENDENT", policy.dynamicSqlClassification(true, false));
    }

    @Test void scenario11_initialLoadAndCdcMustShareFrontier() {
        assertEquals("SNAPSHOT_CDC_FRONTIER_MISMATCH", policy.initialLoadFrontier("SCN-100", "SCN-110"));
    }

    @Test void scenario12_openLargeTransactionPreventsCatchupClaim() {
        assertEquals("CDC_NOT_CAUGHT_UP", policy.cdcCatchup("LSN-9", "LSN-9", 1));
    }

    @Test void scenario13_unsupportedUncontrolledDdlFailsReplication() {
        assertEquals("DDL_REPLICATION_FAILED", policy.ddlDuringCdc(false, false, false));
    }

    @Test void scenario14_unexpressibleTargetTypeBlocksReverseReplication() {
        assertEquals("REVERSE_REPLICATION_UNAVAILABLE", policy.reverseReplication(false, false));
    }

    @Test void scenario15_equalResultsDoNotHidePerformanceRegression() {
        assertEquals("QUERY_PERFORMANCE_REGRESSION", policy.queryGate(true, 20, 900, 15));
    }

    @Test void scenario16_preservedSourceDuplicateIsBaselineDefect() {
        assertEquals(QualityGate.PASS_WITH_BASELINE_DEFECTS,
                policy.preservedSourceDefect(true, true, false));
    }

    @Test void scenario17_migrationIntroducedNullFailsQualityGate() {
        assertEquals(QualityGate.FAIL_MIGRATION_REGRESSION, policy.introducedNull(0, 1));
    }

    @Test void scenario18_deltaProtocolMustSupportOldReadersAndWriters() {
        assertEquals("PROTOCOL_UPGRADE_BLOCKED", policy.deltaProtocolUpgrade(3, 7, 2, 7));
    }

    @Test void scenario19_unratifiedIcebergSpecIsBlockedByDefault() {
        assertEquals("UNRATIFIED_SPECIFICATION_BLOCKED",
                policy.icebergSpecification(4, Set.of(1, 2, 3), false));
    }

    @Test void scenario20_cdcSmallFilesRequireCompactionStrategy() {
        assertEquals("SMALL_FILE_FINDING", policy.smallFileFinding(1_000_000, 128_000_000, 10_000));
    }

    @Test void scenario21_metricDefinitionDriftNeedsOwnerApproval() {
        assertEquals("BI_METRIC_DIFFERENCE",
                policy.metricComparison("gross-revenue-including-refunds", "net-revenue-excluding-refunds", false));
    }

    @Test void scenario22_rowSecurityLossIsCritical() {
        assertEquals("CRITICAL_DATA_SECURITY_FAILURE",
                policy.rowSecurity(Set.of("cn-east"), Set.of("cn-east", "eu-west")));
    }

    @Test void scenario23_deletionMustPropagateThroughLineage() {
        assertEquals("DELETE_PROPAGATION_FAILED", policy.deletionPropagation(
                List.of("transaction", "lakehouse", "bi-extract"), List.of("transaction"), false));
    }

    @Test void scenario24_unknownSourceWriterBlocksDecommission() {
        assertEquals("UNKNOWN_DATABASE_WRITER",
                policy.unknownWriter(Map.of("known-app", 0L, "nightly-script", 2L)));
    }
}
