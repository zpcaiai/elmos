package io.elmos.databasedata;

import java.util.LinkedHashMap;
import java.util.List;

import static io.elmos.databasedata.DatabaseDataModels.*;

public final class DatabaseCutoverAdjudicator {
    public CutoverDecision evaluate(CutoverEvidence evidence) {
        var gates = new LinkedHashMap<String, String>();
        var blockers = new java.util.ArrayList<String>();
        gate(gates, blockers, "INITIAL_LOAD", evidence.initialLoadComplete());
        gate(gates, blockers, "SNAPSHOT_CDC_FRONTIER", evidence.snapshotFrontierConsistent());
        gate(gates, blockers, "CDC_HEALTH", evidence.cdcHealthy());
        gate(gates, blockers, "CDC_OFFSET_RECOVERY", evidence.offsetRecoverable());
        gate(gates, blockers, "CDC_LAG", evidence.lagWithinThreshold());
        gate(gates, blockers, "DATA_RECONCILIATION", evidence.reconciliationPassed());
        gate(gates, blockers, "QUERY_RESULT", evidence.queryResultsPassed());
        gate(gates, blockers, "QUERY_PERFORMANCE", evidence.queryPerformancePassed());
        gate(gates, blockers, "DATA_QUALITY", evidence.dataQualityPassed());
        gate(gates, blockers, "BI_METRIC", evidence.biMetricPassed());
        gate(gates, blockers, "BI_SECURITY", evidence.biSecurityPassed());
        gate(gates, blockers, "GOVERNANCE", evidence.governancePassed());
        gate(gates, blockers, "WRITER_INVENTORY", evidence.writerInventoryComplete());
        gate(gates, blockers, "DDL_CONTROL", evidence.ddlControlled());
        gate(gates, blockers, "ROLLBACK_PATH", evidence.rollbackPathValidated());
        gate(gates, blockers, "SOURCE_WRITE_CONTROL", evidence.sourceWriteControlled());
        if (evidence.evidenceRefs().isEmpty()) blockers.add("DATABASE_CUTOVER_EVIDENCE_MISSING");
        if (!blockers.isEmpty()) {
            return new CutoverDecision(CutoverStatus.CUTOVER_BLOCKED, false, blockers,
                    evidence.evidenceRefs(), gates);
        }
        if (evidence.approvedBy() == null || evidence.approvedBy().isBlank()) {
            return new CutoverDecision(CutoverStatus.CUTOVER_READY_WITH_CONDITIONS, false,
                    List.of("NAMED_WRITE_CUTOVER_APPROVAL_REQUIRED"), evidence.evidenceRefs(), gates);
        }
        return new CutoverDecision(CutoverStatus.CUTOVER_READY, false, List.of(),
                evidence.evidenceRefs(), gates);
    }

    private void gate(LinkedHashMap<String, String> gates, List<String> blockers, String name, boolean passed) {
        gates.put(name, passed ? "PASS" : "FAIL");
        if (!passed) blockers.add(name + "_FAILED");
    }
}
