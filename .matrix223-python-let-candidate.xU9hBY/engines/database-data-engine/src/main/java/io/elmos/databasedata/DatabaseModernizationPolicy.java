package io.elmos.databasedata;

import java.math.BigInteger;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

import static io.elmos.databasedata.DatabaseDataModels.QualityGate;

/** Deterministic Batch 15 policy core. It evaluates evidence but never connects to customer systems. */
public final class DatabaseModernizationPolicy {
    public String oracleEmptyStringRisk(boolean applicationDependsOnEmptyStringAsNull) {
        return applicationDependsOnEmptyStringAsNull ? "EMPTY_STRING_NULL_SEMANTIC_RISK" : "NO_OBSERVED_DEPENDENCY";
    }

    public String oracleNumberMapping(Integer precision, Integer scale) {
        return precision == null || scale == null ? "PROFILE_AND_USAGE_REQUIRED" : "DECIMAL(" + precision + "," + scale + ")";
    }

    public String clusteredIndexStrategy(boolean heterogeneousTarget) {
        return heterogeneousTarget ? "REBUILD_FROM_TARGET_WORKLOAD" : "PRESERVE_VENDOR_INTENT_AND_VALIDATE";
    }

    public String schedulerJobDecision(boolean schedule, boolean credential, boolean steps, boolean retry, boolean timezone) {
        return schedule && credential && steps && retry && timezone ? "JOB_MIGRATION_CANDIDATE" : "JOB_INVENTORY_INCOMPLETE";
    }

    public String mysqlUnsignedMapping(BigInteger observedMaximum, BigInteger targetMaximum) {
        Objects.requireNonNull(observedMaximum); Objects.requireNonNull(targetMaximum);
        return observedMaximum.compareTo(targetMaximum) > 0 ? "NUMERIC_RANGE_RISK" : "RANGE_VALIDATED";
    }

    public String sqlModeDecision(String production, String baseline) {
        return Objects.equals(production, baseline) ? "SQL_MODE_BOUND" : "SQL_MODE_BEHAVIOR_DIFFERENCE";
    }

    public String extensionCompatibility(Set<String> required, Set<String> supported) {
        return supported.containsAll(required) ? "EXTENSIONS_SUPPORTED" : "TARGET_INCOMPATIBLE";
    }

    public String procedureComplexity(boolean packageState, boolean cursor, boolean autonomousTransaction) {
        return packageState || cursor || autonomousTransaction ? "CRITICAL_MANUAL_REDESIGN" : "CONVERSION_CANDIDATE";
    }

    public String triggerStrategy(Set<String> sideEffects, Set<String> coveredSideEffects) {
        return coveredSideEffects.containsAll(sideEffects) ? "TRIGGER_INTENT_COVERED" : "TRIGGER_SIDE_EFFECT_UNRESOLVED";
    }

    public String dynamicSqlClassification(boolean runtimeObjectName, boolean constantText) {
        if (runtimeObjectName) return "RUNTIME_DEPENDENT";
        return constantText ? "PARSED_CONSTANT" : "UNRESOLVED";
    }

    public String initialLoadFrontier(String snapshotPosition, String cdcStartPosition) {
        return Objects.equals(snapshotPosition, cdcStartPosition) ? "FRONTIER_CONSISTENT" : "SNAPSHOT_CDC_FRONTIER_MISMATCH";
    }

    public String cdcCatchup(String sourcePosition, String appliedPosition, int openTransactions) {
        return Objects.equals(sourcePosition, appliedPosition) && openTransactions == 0 ? "CAUGHT_UP" : "CDC_NOT_CAUGHT_UP";
    }

    public String ddlDuringCdc(boolean providerSupportsDdl, boolean approvedManualApply, boolean ddlFrozen) {
        return providerSupportsDdl || approvedManualApply || ddlFrozen ? "DDL_CONTROLLED" : "DDL_REPLICATION_FAILED";
    }

    public String reverseReplication(boolean targetTypeExpressibleAtSource, boolean reversePathTested) {
        return targetTypeExpressibleAtSource && reversePathTested ? "ROLLBACK_PATH_VALIDATED" : "REVERSE_REPLICATION_UNAVAILABLE";
    }

    public String queryGate(boolean resultsEqual, long sourceP95Ms, long targetP95Ms, double maximumRegressionPercent) {
        if (!resultsEqual) return "QUERY_RESULT_FAILED";
        double regression = sourceP95Ms == 0 ? Double.POSITIVE_INFINITY
                : ((double) targetP95Ms - sourceP95Ms) * 100.0 / sourceP95Ms;
        return regression > maximumRegressionPercent ? "QUERY_PERFORMANCE_REGRESSION" : "QUERY_GATE_PASS";
    }

    public QualityGate preservedSourceDefect(boolean sourceDefect, boolean targetDefect, boolean introducedByMigration) {
        if (introducedByMigration) return QualityGate.FAIL_MIGRATION_REGRESSION;
        if (sourceDefect && targetDefect) return QualityGate.PASS_WITH_BASELINE_DEFECTS;
        return sourceDefect == targetDefect ? QualityGate.PASS : QualityGate.HUMAN_REVIEW_REQUIRED;
    }

    public QualityGate introducedNull(long sourceNulls, long targetNulls) {
        return targetNulls > sourceNulls ? QualityGate.FAIL_MIGRATION_REGRESSION : QualityGate.PASS;
    }

    public String deltaProtocolUpgrade(int requiredReader, int requiredWriter, int oldestReader, int oldestWriter) {
        return oldestReader >= requiredReader && oldestWriter >= requiredWriter
                ? "PROTOCOL_COMPATIBLE" : "PROTOCOL_UPGRADE_BLOCKED";
    }

    public String icebergSpecification(int requestedVersion, Set<Integer> ratifiedVersions, boolean experimentalPolicy) {
        return ratifiedVersions.contains(requestedVersion) ? "SPECIFICATION_SUPPORTED"
                : experimentalPolicy ? "EXPERIMENTAL_ISOLATION_REQUIRED" : "UNRATIFIED_SPECIFICATION_BLOCKED";
    }

    public String smallFileFinding(long averageFileBytes, long targetFileBytes, long fileCount) {
        return fileCount > 100 && averageFileBytes < Math.max(1, targetFileBytes / 10)
                ? "SMALL_FILE_FINDING" : "FILE_LAYOUT_ACCEPTABLE";
    }

    public String metricComparison(String sourceExpression, String targetExpression, boolean ownerApproved) {
        if (Objects.equals(sourceExpression, targetExpression)) return "METRIC_EQUIVALENT";
        return ownerApproved ? "METRIC_CHANGE_APPROVED" : "BI_METRIC_DIFFERENCE";
    }

    public String rowSecurity(Set<String> sourceEffectiveRows, Set<String> targetEffectiveRows) {
        return sourceEffectiveRows.equals(targetEffectiveRows) ? "BI_SECURITY_PASS" : "CRITICAL_DATA_SECURITY_FAILURE";
    }

    public String deletionPropagation(Collection<String> requiredAssets, Collection<String> deletedAssets, boolean legalHold) {
        if (legalHold) return "LEGAL_HOLD_RECORDED";
        return deletedAssets.containsAll(requiredAssets) ? "DELETE_PROPAGATION_PASS" : "DELETE_PROPAGATION_FAILED";
    }

    public String unknownWriter(Map<String, Long> observedWritesAfterApplicationCutover) {
        return observedWritesAfterApplicationCutover.values().stream().mapToLong(Long::longValue).sum() == 0
                ? "WRITER_INVENTORY_CLEAR" : "UNKNOWN_DATABASE_WRITER";
    }

    public List<String> canonicalIrStages() {
        return List.of("VENDOR_PARSER", "VENDOR_AST", "CANONICAL_IR", "TARGET_AST", "TARGET_SQL");
    }
}
