package io.elmos.controlplane;

import io.elmos.composite.ProgressiveTrafficController.*;
import io.elmos.composite.SystemCutoverOrchestrator.DecommissionEvidence;
import org.junit.jupiter.api.Test;

import java.util.List;

import static io.elmos.composite.CompositeModels.TrafficDecision;
import static org.junit.jupiter.api.Assertions.*;

class CompositeControllerTest {
    private final CompositeController controller = new CompositeController();

    @Test void exposesTheFourExecutionEnginesAndSystemResponsibilities() {
        var capabilities = controller.capabilities();
        assertEquals(4, capabilities.languageEngines().size());
        assertTrue(capabilities.prohibitedActions().contains("EDIT_SOURCE"));
        assertTrue(capabilities.prohibitedActions().contains("AUTO_SWITCH_PRODUCTION_WRITES"));
    }

    @Test void fullTrafficCannotBeAutomaticallyPromoted() {
        GateEvidence gates = new GateEvidence(true, true, true, true, true, true, true, true,
                true, true, true, true, false, true, false, false, List.of("gate-ev"));
        var decision = controller.evaluateTraffic(new TrafficStageRequest(Provider.SERVICE_MESH,
                Stage.CANARY_50, Stage.FULL_TRAFFIC, Cohort.LOW_RISK_TENANT, gates, false));
        assertEquals(TrafficDecision.HUMAN_REVIEW, decision.decision());
        assertFalse(decision.automatic());
    }

    @Test void decommissionEvaluationIsFailClosed() {
        var decision = controller.evaluateDecommission(new DecommissionEvidence(true, true, true,
                false, true, true, true, true, true, true, true, true, true, List.of("ev")));
        assertFalse(decision.allowed());
        assertTrue(decision.permittedActions().isEmpty());
    }
}
