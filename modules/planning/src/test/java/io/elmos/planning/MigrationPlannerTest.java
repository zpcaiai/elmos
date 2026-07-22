package io.elmos.planning;

import io.elmos.health.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class MigrationPlannerTest {
    @TempDir Path root;
    private final Clock clock = Clock.fixed(Instant.parse("2026-07-20T00:00:00Z"), ZoneOffset.UTC);

    @Test void buildsDeterministicDagWavesRangesAndApprovalGates() throws Exception {
        Files.writeString(root.resolve("pom.xml"), "<project><modelVersion>4.0.0</modelVersion><parent><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-parent</artifactId><version>2.7.18</version></parent><groupId>x</groupId><artifactId>a</artifactId><version>1</version><properties><java.version>8</java.version></properties><dependencies><dependency><groupId>org.junit.jupiter</groupId><artifactId>junit-jupiter</artifactId><version>5.10.0</version><scope>test</scope></dependency></dependencies></project>");
        Path main = root.resolve("src/main/java/x/A.java"); Files.createDirectories(main.getParent()); Files.writeString(main, "package x; import javax.persistence.Entity; public class A {}");
        Path test = root.resolve("src/test/java/x/ATest.java"); Files.createDirectories(test.getParent()); Files.writeString(test, "package x; class ATest {}");
        var provider = (HealthModels.VulnerabilityProvider) dependencies -> new HealthModels.VulnerabilityQueryResult(List.of(),
                new HealthModels.VulnerabilityEvidence(HealthModels.EvidenceStatus.PASS, "fixture", clock.instant(), "1", null));
        var health = new JavaLegacyHealthCheck(ScanPolicy.defaults(), provider, clock).scan(new JavaLegacyHealthCheck.Request("snapshot-1", root));
        MigrationPlanner planner = new MigrationPlanner(new CompatibilityMatrix("matrix-2026-07"));
        var first = planner.plan(health, PlanningModels.OrganizationPolicy.defaults());
        var second = planner.plan(health, PlanningModels.OrganizationPolicy.defaults());
        assertEquals(first.planId(), second.planId()); assertEquals(9, first.steps().size());
        assertEquals(List.of(), first.steps().getFirst().dependsOn());
        assertTrue(first.steps().stream().filter(s -> !s.dependsOn().isEmpty()).allMatch(s -> s.dependsOn().stream().allMatch(id -> first.steps().stream().anyMatch(parent -> parent.stepId().equals(id)))));
        assertFalse(first.waves().isEmpty()); assertTrue(first.totalEffort().maximumPersonDays() > first.totalEffort().likelyPersonDays());
        assertTrue(first.approvalGates().stream().anyMatch(g -> g.type() == PlanningModels.GateType.DATA_REVIEW));
        assertEquals(21, first.target().javaVersion());
    }

    @Test void blocksPlanWhenRequiredEvidenceIsUnknown() {
        var health = new HealthModels.LegacyHealthReport("1.0", "h", "s", clock.instant(), HealthModels.BuildSystem.UNKNOWN, null, null, null,
                List.of(), List.of(), List.of(), new HealthModels.VulnerabilityEvidence(HealthModels.EvidenceStatus.INCONCLUSIVE, "NONE", clock.instant(), null, "missing"),
                List.of(), List.of(), new HealthModels.TestReadiness(0,0,false,false,false,0, HealthModels.EvidenceStatus.INCONCLUSIVE),
                new HealthModels.TargetRecommendation(21,null,"default", HealthModels.EvidenceStatus.INCONCLUSIVE,List.of()), 0,
                HealthModels.Severity.CRITICAL, HealthModels.EvidenceStatus.INCONCLUSIVE, List.of());
        var plan = new MigrationPlanner(new CompatibilityMatrix("v1")).plan(health, PlanningModels.OrganizationPolicy.defaults());
        assertEquals(PlanningModels.PlanStatus.BLOCKED, plan.status());
        assertTrue(plan.blockingReasons().contains("BUILD_SYSTEM_UNKNOWN"));
        assertTrue(plan.blockingReasons().contains("VULNERABILITY_EVIDENCE_INCOMPLETE"));
        assertTrue(plan.approvalGates().stream().anyMatch(gate -> gate.gateId().equals("gate-build-evidence") && gate.blocking()));
        assertTrue(plan.approvalGates().stream().anyMatch(gate -> gate.gateId().equals("gate-vulnerability-evidence") && gate.blocking()));
    }
}
