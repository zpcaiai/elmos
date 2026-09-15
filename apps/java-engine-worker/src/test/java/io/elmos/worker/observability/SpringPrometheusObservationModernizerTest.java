package io.elmos.worker.observability;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringPrometheusObservationModernizerTest {

    @Test
    void testPrometheusObservationModernizationFlow(@TempDir Path tempDir) throws IOException {
        // 1. Setup pom.xml
        Path pomPath = tempDir.resolve("pom.xml");
        String pomContent = """
                <project>
                    <dependencies>
                        <dependency>
                            <groupId>org.springframework.boot</groupId>
                            <artifactId>spring-boot-starter-actuator</artifactId>
                        </dependency>
                    </dependencies>
                </project>
                """;
        Files.writeString(pomPath, pomContent);

        // 2. Setup application.yml
        Path resDir = tempDir.resolve("src/main/resources");
        Files.createDirectories(resDir);
        Path ymlPath = resDir.resolve("application.yml");
        Files.writeString(ymlPath, "spring:\n  application:\n    name: payment-service\n");

        // Execute modernization
        SpringPrometheusObservationModernizer modernizer = new SpringPrometheusObservationModernizer();
        SpringPrometheusObservationModernizer.PrometheusModernizationResult result = modernizer.modernize(tempDir);

        assertTrue(result.modified(), "Workspace should be modified");
        assertTrue(result.changesCount() >= 5, "Should apply at least 5 changes");

        // Verify pom.xml has micrometer-registry-prometheus
        String updatedPom = Files.readString(pomPath);
        assertTrue(updatedPom.contains("micrometer-registry-prometheus"), "Should inject micrometer-registry-prometheus dependency");

        // Verify application.yml has Prometheus actuator config
        String updatedYml = Files.readString(ymlPath);
        assertTrue(updatedYml.contains("include: health,info,prometheus,metrics"), "Should expose prometheus endpoint");
        assertTrue(updatedYml.contains("http.server.requests: true"), "Should enable percentiles histogram");

        // Verify PrometheusMetricAliasFilterConfig.java generated
        Path filterFile = tempDir.resolve("src/main/java/io/elmos/generated/config/PrometheusMetricAliasFilterConfig.java");
        assertTrue(Files.exists(filterFile), "PrometheusMetricAliasFilterConfig should be generated");
        String filterContent = Files.readString(filterFile);
        assertTrue(filterContent.contains("MeterFilter.rename"), "Should use MeterFilter.rename for aliasing");

        // Verify Grafana Dashboard generated
        Path dashboardFile = tempDir.resolve("deploy/observability/grafana-dashboard-spring-boot-3.json");
        assertTrue(Files.exists(dashboardFile), "Grafana dashboard json should be generated");
        String dashboardContent = Files.readString(dashboardFile);
        assertTrue(dashboardContent.contains("HTTP Request Throughput"), "Dashboard should monitor HTTP RPS");
        assertTrue(dashboardContent.contains("hikaricp_connections_active"), "Dashboard should monitor HikariCP");

        // Verify AlertManager rules generated
        Path alertFile = tempDir.resolve("deploy/observability/prometheus-alerts-spring-boot-3.yml");
        assertTrue(Files.exists(alertFile), "Prometheus alert rules yaml should be generated");
        String alertContent = Files.readString(alertFile);
        assertTrue(alertContent.contains("HighHttp5xxErrorRate"), "Should contain HighHttp5xxErrorRate alert");
        assertTrue(alertContent.contains("HikariConnectionPoolStarvation"), "Should contain HikariConnectionPoolStarvation alert");
    }
}
