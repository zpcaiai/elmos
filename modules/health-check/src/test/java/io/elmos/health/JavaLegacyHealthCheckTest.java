package io.elmos.health;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class JavaLegacyHealthCheckTest {
    @TempDir Path root;
    private final Clock clock = Clock.fixed(Instant.parse("2026-07-20T00:00:00Z"), ZoneOffset.UTC);

    @Test void discoversMavenSpringJavaRisksApisAndTestsWithoutInventingCves() throws Exception {
        Files.writeString(root.resolve("pom.xml"), """
                <project><modelVersion>4.0.0</modelVersion><parent><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-parent</artifactId><version>2.7.18</version></parent>
                <groupId>example</groupId><artifactId>legacy</artifactId><version>1</version><properties><java.version>8</java.version></properties>
                <dependencies><dependency><groupId>org.junit.jupiter</groupId><artifactId>junit-jupiter</artifactId><version>5.10.0</version><scope>test</scope></dependency>
                <dependency><groupId>x</groupId><artifactId>conflict</artifactId><version>1</version></dependency><dependency><groupId>x</groupId><artifactId>conflict</artifactId><version>2</version></dependency></dependencies></project>
                """);
        Path source = root.resolve("src/main/java/example/LegacyController.java"); Files.createDirectories(source.getParent());
        Files.writeString(source, """
                package example;
                import javax.persistence.Entity;
                @RestController class LegacyController {
                  @GetMapping("/legacy") public String get(){ return "ok"; }
                  @Transactional private void save(){}
                }
                """);
        Path test = root.resolve("src/test/java/example/LegacyControllerTest.java"); Files.createDirectories(test.getParent()); Files.writeString(test, "package example; class LegacyControllerTest {}");
        JavaLegacyHealthCheck scanner = new JavaLegacyHealthCheck(ScanPolicy.defaults(), VulnerabilityProviders.notConfigured(clock), clock);
        HealthModels.LegacyHealthReport report = scanner.scan(new JavaLegacyHealthCheck.Request("snapshot-1", root));
        assertEquals(HealthModels.BuildSystem.MAVEN, report.buildSystem());
        assertEquals("8", report.detectedJavaVersion()); assertEquals("2.7.18", report.springBootVersion());
        assertTrue(report.findings().stream().anyMatch(f -> f.code().equals("LEGACY_JAVAX_API")));
        assertTrue(report.findings().stream().anyMatch(f -> f.code().equals("DEPENDENCY_VERSION_CONFLICT")));
        assertFalse(report.publicApis().isEmpty()); assertEquals(0, report.vulnerabilities().size());
        assertEquals(HealthModels.EvidenceStatus.INCONCLUSIVE, report.vulnerabilityEvidence().status());
        assertEquals(21, report.targetRecommendation().javaVersion());
    }

    @Test void rejectsDoctypeAndRootSymlink() throws Exception {
        Files.writeString(root.resolve("pom.xml"), "<!DOCTYPE foo [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]><project><artifactId>&xxe;</artifactId></project>");
        HealthModels.LegacyHealthReport report = new JavaLegacyHealthCheck(ScanPolicy.defaults(), VulnerabilityProviders.notConfigured(clock), clock)
                .scan(new JavaLegacyHealthCheck.Request("snapshot-2", root));
        assertTrue(report.findings().stream().anyMatch(f -> f.code().equals("POM_PARSE_FAILED") && f.status() == HealthModels.EvidenceStatus.INCONCLUSIVE));
        Path link = root.resolveSibling(root.getFileName() + "-link");
        try { Files.createSymbolicLink(link, root); assertThrows(SecurityException.class, () -> new ProjectDiscovery(ScanPolicy.defaults()).discover(link)); }
        finally { Files.deleteIfExists(link); }
    }

    @Test void consumesProviderEvidenceAndVulnerabilities() throws Exception {
        Files.writeString(root.resolve("pom.xml"), "<project><modelVersion>4.0.0</modelVersion><groupId>x</groupId><artifactId>a</artifactId><version>1</version><properties><maven.compiler.release>17</maven.compiler.release></properties><dependencies><dependency><groupId>g</groupId><artifactId>a</artifactId><version>1</version></dependency></dependencies></project>");
        var provider = (HealthModels.VulnerabilityProvider) dependencies -> new HealthModels.VulnerabilityQueryResult(
                List.of(new HealthModels.Vulnerability("OSV-1", "g:a:1", HealthModels.Severity.CRITICAL, "known", "https://osv.dev/OSV-1", "2", clock.instant())),
                new HealthModels.VulnerabilityEvidence(HealthModels.EvidenceStatus.PASS, "OSV", clock.instant(), "2026-07-20", null));
        var report = new JavaLegacyHealthCheck(ScanPolicy.defaults(), provider, clock).scan(new JavaLegacyHealthCheck.Request("s", root));
        assertEquals(HealthModels.Severity.CRITICAL, report.overallRisk()); assertEquals(1, report.vulnerabilities().size());
    }
}
