package io.elmos.controlplane;

import io.elmos.application.CrossDomainDecisionGovernance;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class CrossDomainGovernanceControllerTest {
    @Test void controllerCannotAutoApproveOrExecute() {
        var result = new CrossDomainGovernanceController().evaluate(new CrossDomainDecisionGovernance.Request(
                "org", CrossDomainDecisionGovernance.Domain.ENTERPRISE_ARCHITECTURE,
                "INVESTMENT", List.of(), List.of(), true));
        assertEquals(CrossDomainDecisionGovernance.Status.BLOCKED, result.status());
        assertFalse(result.eligibleForExecution());
        assertFalse(result.humanDecisionGranted());
        assertFalse(result.productionStateChanged());
    }
}
