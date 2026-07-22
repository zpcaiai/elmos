package io.elmos.controlplane;

import io.elmos.application.DatabaseDataCutoverGovernance;
import org.junit.jupiter.api.Test;

import java.util.List;

import static io.elmos.application.DatabaseDataCutoverGovernance.Decision.*;
import static io.elmos.application.DatabaseDataCutoverGovernance.Stage.*;
import static org.junit.jupiter.api.Assertions.*;

class DatabaseDataControllerTest {
    private final DatabaseDataController controller = new DatabaseDataController();

    @Test void keepsDatabaseExecutionAndWriterSwitchOutOfControlPlane() {
        var capabilities = controller.capabilities();
        assertEquals("ELMOS_DATABASE_DATA", capabilities.engine());
        assertEquals(List.of("OLTP_DATABASE", "ANALYTICS_PLATFORM", "BI_SEMANTIC"), capabilities.tracks());
        assertTrue(capabilities.prohibitedActions().contains("CONNECT_TO_CUSTOMER_DATABASE"));
        assertTrue(capabilities.prohibitedActions().contains("SWITCH_AUTHORITATIVE_WRITER"));
        assertTrue(capabilities.status().contains("NOT_CONFIGURED"));
    }

    @Test void writeCutoverRequiresEveryDataGateAndNamedApproval() {
        var evidence = evidence(READ_CUTOVER, WRITE_CUTOVER, true, null);
        assertEquals(HUMAN_REVIEW, controller.evaluateCutover(evidence).decision());
        assertEquals(ADVANCE, controller.evaluateCutover(
                evidence(READ_CUTOVER, WRITE_CUTOVER, true, "database-owner")).decision());
        var blocked = controller.evaluateCutover(evidence(READ_CUTOVER, WRITE_CUTOVER, false, "database-owner"));
        assertEquals(HOLD, blocked.decision());
        assertTrue(blocked.blockers().contains("QUERY_PERFORMANCE_FAILED"));
    }

    private DatabaseDataCutoverGovernance.Evidence evidence(
            DatabaseDataCutoverGovernance.Stage current,
            DatabaseDataCutoverGovernance.Stage requested,
            boolean performance,
            String approval) {
        return new DatabaseDataCutoverGovernance.Evidence("org-1", current, requested,
                true, true, true, performance, true, true, true, true, true, true,
                true, true, true, List.of("evidence://database-cutover"), approval);
    }
}
