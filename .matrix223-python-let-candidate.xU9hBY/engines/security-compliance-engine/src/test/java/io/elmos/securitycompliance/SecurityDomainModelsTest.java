package io.elmos.securitycompliance;

import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class SecurityDomainModelsTest {
    @Test void vulnerabilityFindingExposureAndRiskRemainDistinct() {
        var finding = new SecurityDomainModels.SecurityFinding("finding-1", "asset-1", "DEPENDENCY",
                SecurityDomainModels.Severity.HIGH, .9, "CONFIRMED", "sca", "rule-1", List.of("evidence://finding"));
        var vulnerability = new SecurityDomainModels.Vulnerability("CVE-example", List.of("GHSA-example"), "pkg:maven/a@1");
        var exposure = new SecurityDomainModels.Exposure("exposure-1", vulnerability.vulnerabilityId(), finding.assetId(),
                SecurityDomainModels.Reachability.NOT_LOADED, false, false, List.of("evidence://artifact"));
        var risk = new SecurityDomainModels.VulnerabilityRisk(vulnerability.vulnerabilityId(), finding.assetId(), "MEDIUM", 5,
                List.of("KEV_SIGNAL", "NOT_LOADED"), SecurityDomainModels.RiskDecision.INVESTIGATE,
                exposure.reachability(), List.of("evidence://risk"));
        assertEquals("CVE-example", vulnerability.vulnerabilityId()); assertEquals(SecurityDomainModels.Reachability.NOT_LOADED, risk.reachability());
    }

    @Test void parseErrorsCannotBecomePass() {
        var coverage = new SecurityDomainModels.ScanCoverage(100, 70, 0, 30, 0, Map.of());
        assertEquals(SecurityModels.ExternalStatus.COVERAGE_INSUFFICIENT, coverage.status(0));
    }

    @Test void notAffectedVexRequiresEvidenceAndExpiry() {
        assertThrows(IllegalArgumentException.class, () -> new SecurityDomainModels.VexStatement("product", "component", "CVE",
                SecurityDomainModels.VexStatus.NOT_AFFECTED, "not in path", "reachability", "reviewer",
                Instant.parse("2099-01-01T00:00:00Z"), "artifact changed", List.of()));
    }

    @Test void riskExceptionIsOwnedApprovedScopedAndExpiring() {
        var exception = new SecurityDomainModels.RiskException("exception-1", "service-owner", "asset-1", "patch unavailable",
                "maintain service while isolated", "control-network-block", "limited availability",
                Instant.parse("2026-07-21T00:00:00Z"), Instant.parse("2026-08-21T00:00:00Z"),
                "sha256:artifact", "abc123", "production", "risk-owner", List.of("evidence://exception"));
        assertTrue(exception.expiresAt().isAfter(exception.startsAt()));
    }
}
