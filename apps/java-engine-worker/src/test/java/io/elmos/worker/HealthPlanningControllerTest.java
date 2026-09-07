package io.elmos.worker;

import io.elmos.health.*;
import io.elmos.planning.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class HealthPlanningControllerTest {
    @TempDir Path workspace;
    @Test void executesRealHealthAndPlanningAgainstWorkspaceBoundPath() throws Exception {
        Path project = workspace.resolve("project"); Files.createDirectories(project);
        Files.writeString(project.resolve("pom.xml"), "<project><modelVersion>4.0.0</modelVersion><groupId>x</groupId><artifactId>a</artifactId><version>1</version><properties><java.version>11</java.version></properties></project>");
        Clock clock = Clock.fixed(Instant.parse("2026-07-20T00:00:00Z"), ZoneOffset.UTC);
        var provider = (HealthModels.VulnerabilityProvider) dependencies -> new HealthModels.VulnerabilityQueryResult(List.of(),
                new HealthModels.VulnerabilityEvidence(HealthModels.EvidenceStatus.PASS, "fixture", clock.instant(), "v1", null));
        var controller = new HealthPlanningController(new JavaLegacyHealthCheck(ScanPolicy.defaults(), provider, clock),
                new MigrationPlanner(new CompatibilityMatrix("v1")), new WorkspacePathResolver(workspace));
        var report = controller.health(new HealthPlanningController.AnalysisRequest("snapshot", "project"));
        var plan = controller.plan(new HealthPlanningController.AnalysisRequest("snapshot", "project"));
        assertEquals("11", report.detectedJavaVersion()); assertEquals(report.snapshotId(), plan.snapshotId()); assertEquals(9, plan.steps().size());
        assertThrows(SecurityException.class, () -> controller.health(new HealthPlanningController.AnalysisRequest("snapshot", "../")));
    }
}
