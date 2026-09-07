package io.elmos.controlplane;

import io.elmos.application.SuiteCutoverGovernance;
import org.junit.jupiter.api.Test;

import java.util.HashSet;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class EnterpriseSuiteControllerTest {
    private final EnterpriseSuiteController controller = new EnterpriseSuiteController();

    @Test void controlPlaneIsJudgeNotSuiteExecutor() {
        var capabilities = controller.capabilities();
        assertEquals("ELMOS_ENTERPRISE_SUITE", capabilities.engine());
        assertFalse(capabilities.executesSuiteChanges());
        assertTrue(capabilities.prohibitedDirectActions().contains("PUBLISH_PRODUCTION_TRANSPORT"));
        assertTrue(capabilities.prohibitedDirectActions().contains("AUTO_CUTOVER"));
    }

    @Test void decommissionBlocksWhileAuditArchiveIsUnavailable() {
        var gates = new HashSet<>(SuiteCutoverGovernance.cutoverGateNames());
        gates.addAll(SuiteCutoverGovernance.decommissionGateNames());
        gates.remove("AUDIT_HISTORY_ACCESSIBLE");
        var result = controller.evaluateDecommission(new SuiteCutoverGovernance.Evidence(
                "sha", "sha", true, gates, List.of("evidence://suite")));
        assertEquals(SuiteCutoverGovernance.Decision.FAIL, result.decision());
        assertTrue(result.blockers().contains("AUDIT_HISTORY_NOT_ACCESSIBLE"));
    }
}
