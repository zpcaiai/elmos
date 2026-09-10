package io.elmos.worker.validation;

import io.elmos.worker.corpus.SpringThirtyOpenSourceProjectsCorpus.ProjectDomain;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class SpringEnterpriseRegressionVerificationMatrixTest {

    @Test
    void testMatrixEvaluation() {
        var summary = SpringEnterpriseRegressionVerificationMatrix.evaluateMatrix();

        assertTrue(summary.totalCellsEvaluated() >= 80, "Matrix must cover at least 80 combinations");
        assertEquals(summary.totalCellsEvaluated(), summary.certifiedCellsCount());
        assertEquals(100.0, summary.overallPassRate());
        assertTrue(summary.isProductionReady());
        assertTrue(summary.averagePerformanceRatio() <= 1.05);
    }

    @Test
    void testDomainSpecificCells() {
        var secCells = SpringEnterpriseRegressionVerificationMatrix.getCellsForDomain(
                ProjectDomain.SECURITY_ENTERPRISE);

        assertFalse(secCells.isEmpty());
        for (var cell : secCells) {
            assertTrue(cell.isCertified());
            assertEquals("4.1.0", cell.targetBootVersion());
            assertEquals("21", cell.targetJavaVersion());
        }
    }
}
