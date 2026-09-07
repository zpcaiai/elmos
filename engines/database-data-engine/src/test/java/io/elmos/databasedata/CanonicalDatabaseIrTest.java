package io.elmos.databasedata;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static io.elmos.databasedata.CanonicalDatabaseIr.*;
import static io.elmos.databasedata.DatabaseDataModels.*;
import static org.junit.jupiter.api.Assertions.*;

class CanonicalDatabaseIrTest {
    private final Provenance provenance = new Provenance(DatabaseVendor.ORACLE, "SALES.ORDERS",
            "1:1-1:80", "sha256-source", List.of("artifact://source/orders"));

    @Test void vendorSpecificSemanticsCannotBeDiscarded() {
        assertThrows(IllegalArgumentException.class, () -> new CanonicalTypeRef(
                CanonicalType.VENDOR_SPECIFIC, null, null, null, true, Map.of()));
        var number = new CanonicalTypeRef(CanonicalType.DECIMAL, null, null, null, true,
                Map.of("source", "ORACLE_NUMBER", "precision", "UNSPECIFIED"));
        assertEquals("ORACLE_NUMBER", number.vendorExtension().get("source"));
    }

    @Test void runtimeDependentSqlCannotBeAutomaticallyEmitted() {
        var sql = new SqlNode("sql-1", SqlOperation.DYNAMIC_SQL, List.of("table-1"),
                DynamicSqlStatus.RUNTIME_DEPENDENT, Map.of("operation", "SELECT"),
                Map.of("runtimeTableName", true), provenance);
        assertFalse(sql.eligibleForAutomaticTargetEmission());
    }

    @Test void packageStateAndAutonomousTransactionsRequireManualRedesign() {
        var procedure = new ProcedureNode("routine-1", "PACKAGE_BODY",
                List.of(new ProcedureStatement("stmt-1", ProcedureOperation.TRANSACTION,
                        List.of("table-1"), Map.of("autonomous", true))),
                true, true, Map.of("packageState", true), provenance);
        assertTrue(procedure.requiresManualRedesign());
    }

    @Test void snapshotRejectsUnknownDependencyAndEvidenceMapsToUnifiedAuthorities() {
        var table = new SchemaObjectNode("table-1", "orders", "sales", "orders",
                "TABLE", List.of(), Map.of(), provenance);
        assertThrows(IllegalArgumentException.class, () -> new Snapshot("1.0", "org-1", "snapshot-1",
                List.of(table), List.of(), List.of(),
                List.of(new DependencyEdge("table-1", "missing", DependencyType.WRITES, "ev"))));

        var extension = new DatabaseDataEvidenceMapper().map(EvidenceType.CDC_STATUS,
                "artifact://cdc/status", List.of("application-pr-1"), Map.of("provider", "DEBEZIUM"));
        assertEquals("DATABASE_DATA_PLATFORM", extension.scope());
        assertEquals("DATA_SYNCHRONIZATION_RISK", extension.risk());
        assertEquals("ELMOS / CDC Readiness", extension.check());
        assertEquals(CostUnit.CDC_STREAM_HOUR, extension.costUnit());
    }
}
