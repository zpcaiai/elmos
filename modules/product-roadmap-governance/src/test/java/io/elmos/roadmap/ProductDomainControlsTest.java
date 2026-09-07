package io.elmos.roadmap;

import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.util.List;

import static io.elmos.roadmap.ProductDomainControls.ControlDecision.*;
import static org.junit.jupiter.api.Assertions.*;

class ProductDomainControlsTest {
    private final ProductDomainControls controls = new ProductDomainControls();

    @Test void tbmRejectsUnreconciledAndDoubleCountedValue() {
        var result = controls.evaluateTbm(new ProductDomainControls.TbmEvidence(
                BigDecimal.TEN, BigDecimal.ONE, BigDecimal.ONE, .5, 0, 1,
                true, false, false, true, true, List.of("ev")));
        assertEquals(BLOCKED, result.decision());
        assertTrue(result.reasonCodes().contains("FINANCIAL_SOURCE_RECONCILIATION_FAILED"));
        assertTrue(result.reasonCodes().contains("BENEFIT_DOUBLE_COUNT_RISK"));
    }

    @Test void workforceProhibitsRankingOpaquePredictionAndAutomatedEmployment() {
        var result = controls.evaluateWorkforce(new ProductDomainControls.WorkforceEvidence(
                1, 1, 0, true, true, true, true, false, false, List.of("ev")));
        assertEquals(BLOCKED, result.decision());
        assertTrue(result.reasonCodes().contains("PERSONAL_RANKING_FORBIDDEN"));
        assertTrue(result.reasonCodes().contains("AUTOMATED_EMPLOYMENT_DECISION_FORBIDDEN"));
    }

    @Test void transformationCannotDeclareSuccessWithoutBehaviorAndRollbackEvidence() {
        var result = controls.evaluateTransformation(new ProductDomainControls.TransformationEvidence(
                1, 1, 1, 1, true, false, true, true, false, true, List.of("ev")));
        assertEquals(BLOCKED, result.decision());
        assertTrue(result.reasonCodes().contains("AUTOMATIC_TRANSFORMATION_SUCCESS_FORBIDDEN"));
    }

    @Test void boundedControlTowerOnlyPreparesHumanReview() {
        var result = controls.evaluateControlTower(new ProductDomainControls.ControlTowerEvidence(
                1, 1, true, true, true, true, true, true, true, false, false, List.of("ev")));
        assertEquals(READY_FOR_HUMAN_REVIEW, result.decision());
        assertFalse(result.humanApprovalGranted());
        assertFalse(result.externalOperationExecuted());
    }

    @Test void autonomousProductionRequestAlwaysFailsClosed() {
        var result = controls.evaluateControlTower(new ProductDomainControls.ControlTowerEvidence(
                1, 1, true, true, true, true, true, true, true, false, true, List.of("ev")));
        assertEquals(BLOCKED, result.decision());
        assertTrue(result.reasonCodes().contains("AUTONOMOUS_PRODUCTION_EXECUTION_FORBIDDEN"));
    }
}
