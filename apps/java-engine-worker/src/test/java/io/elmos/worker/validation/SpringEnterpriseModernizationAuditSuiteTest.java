package io.elmos.worker.validation;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringEnterpriseModernizationAuditSuiteTest {

    @TempDir
    Path tempDir;

    private final SpringEnterpriseModernizationAuditSuite suite = new SpringEnterpriseModernizationAuditSuite();

    @Test
    @DisplayName("Verify Full Audit Suite Across 30 Modernized Enterprise Benchmark Projects")
    void testAuditAllThirtyProjects() throws Exception {
        SpringEnterpriseModernizationAuditSuite.SuiteAuditReport report = suite.auditCorpus(tempDir);

        System.out.println("================================================================================");
        System.out.println("  ENTERPRISE MODERNIZATION AUDIT CERTIFICATION REPORT (30 PROJECTS)");
        System.out.println("================================================================================");
        System.out.printf("Total Projects Scanned:      %d\n", report.totalProjectsAudited());
        System.out.printf("Fully Certified Projects:    %d\n", report.certifiedProjectsCount());
        System.out.printf("Certification Rate:          %.1f%%\n", report.certificationRate());
        System.out.printf("Average Maturity Score:      %.2f / 100.0\n", report.averageMaturityScore());
        System.out.println("--------------------------------------------------------------------------------");

        report.projectVerdicts().forEach((id, verdict) -> {
            System.out.printf("[%s] %s | Sec: %.1f | JPA: %.1f | Cloud: %.1f | XML: %.1f | Overall: %.1f\n",
                    verdict.fullyCertified() ? "CERTIFIED" : "DEFECT",
                    id,
                    verdict.securityScore(),
                    verdict.jpaScore(),
                    verdict.cloudScore(),
                    verdict.xmlScore(),
                    verdict.overallMaturityScore()); if (!verdict.fullyCertified()) verdict.auditLogs().forEach(l -> System.out.println("   " + l)
            );
        });

        System.out.println("================================================================================");

        assertEquals(30, report.totalProjectsAudited());
        assertEquals(30, report.certifiedProjectsCount());
        assertEquals(100.0, report.certificationRate());
        assertTrue(report.allProjectsCertified());
    }
}
