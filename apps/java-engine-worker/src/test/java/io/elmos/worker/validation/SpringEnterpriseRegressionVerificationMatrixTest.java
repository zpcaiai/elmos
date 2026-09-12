package io.elmos.worker.validation;

import io.elmos.worker.corpus.SpringThirtyOpenSourceProjectsCorpus.ProjectDomain;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringEnterpriseRegressionVerificationMatrixTest {

    @Test
    @DisplayName("Evaluate comprehensive regression verification matrix")
    void testEvaluateMatrixCompleteness() {
        var summary = SpringEnterpriseRegressionVerificationMatrix.evaluateMatrix();

        assertNotNull(summary);
        assertTrue(summary.totalCellsEvaluated() > 0);
        assertEquals(summary.totalCellsEvaluated(), summary.certifiedCellsCount(),
                "All matrix cells must achieve certified status");
        assertEquals(100.0, summary.overallPassRate(), 0.001,
                "Overall matrix pass rate must be 100.0%");
        assertTrue(summary.averagePerformanceRatio() <= 1.05,
                "Average performance degradation ratio must be within 5% tolerance");
        assertTrue(summary.isProductionReady(),
                "Matrix must indicate production readiness");
    }

    @Test
    @DisplayName("Verify domain coverage across Security, JPA, Cloud, and XML")
    void testDomainCellDistributions() {
        for (ProjectDomain domain : new ProjectDomain[]{
                ProjectDomain.SECURITY_ENTERPRISE,
                ProjectDomain.JPA_HIBERNATE_COMPLEX,
                ProjectDomain.SPRING_CLOUD_MICROSERVICES,
                ProjectDomain.XML_HYBRID_LEGACY
        }) {
            List<SpringEnterpriseRegressionVerificationMatrix.MatrixCell> cells =
                    SpringEnterpriseRegressionVerificationMatrix.getCellsForDomain(domain);

            assertNotNull(cells);
            assertTrue(cells.size() >= 20, "Domain " + domain + " must have at least 20 verification cells");

            for (var cell : cells) {
                assertEquals(domain, cell.domain());
                assertEquals("4.1.0", cell.targetBootVersion());
                assertEquals("21", cell.targetJavaVersion());
                assertTrue(cell.compilesSuccessfully());
                assertTrue(cell.passesAllUnitTests());
                assertTrue(cell.passesSecurityAudit());
                assertTrue(cell.passesJpaAudit());
                assertTrue(cell.passesCloudAudit());
                assertTrue(cell.passesXmlAudit());
                assertTrue(cell.isCertified());
            }
        }
    }

    @Test
    @DisplayName("Verify specific cell lookup and invariant attributes")
    void testSpecificCellLookup() {
        String cellId = "MATRIX-SECURITY_ENTERPRISE-BOOT_1_5_22_RELEASE-JAVA_8";
        var cell = SpringEnterpriseRegressionVerificationMatrix.getCell(cellId);

        assertNotNull(cell, "Cell " + cellId + " should exist in matrix");
        assertEquals(ProjectDomain.SECURITY_ENTERPRISE, cell.domain());
        assertEquals("1.5.22.RELEASE", cell.sourceBootVersion());
        assertEquals("8", cell.sourceJavaVersion());
        assertEquals("CERTIFIED", cell.certificationStatus());
        assertTrue(cell.isCertified());
    }
}
