package io.elmos.planning;

import io.elmos.health.HealthModels;

import java.util.ArrayList;
import java.util.List;

public final class CompatibilityMatrix {
    private final String version;
    public CompatibilityMatrix(String version) {
        if (version == null || version.isBlank()) throw new IllegalArgumentException("compatibility matrix version is required");
        this.version = version;
    }

    public List<PlanningModels.CompatibilityDecision> resolve(HealthModels.LegacyHealthReport health, PlanningModels.TargetProfile target) {
        List<PlanningModels.CompatibilityDecision> decisions = new ArrayList<>();
        String sourceJava = health.detectedJavaVersion();
        decisions.add(new PlanningModels.CompatibilityDecision("JAVA", sourceJava, Integer.toString(target.javaVersion()),
                sourceJava != null, sourceJava == null || !sourceJava.equals(Integer.toString(target.javaVersion())),
                sourceJava == null ? "Source Java level is unknown and must be measured before execution" : "JDK transition requires baseline build evidence",
                sourceJava == null ? HealthModels.EvidenceStatus.INCONCLUSIVE : HealthModels.EvidenceStatus.PASS, version));
        String boot = health.springBootVersion();
        boolean bootKnown = boot != null; boolean bootMigration = bootKnown && major(boot) < 3;
        decisions.add(new PlanningModels.CompatibilityDecision("SPRING_BOOT", boot, target.springBootLine(),
                bootKnown, bootMigration, bootKnown ? (bootMigration ? "Spring Boot major upgrade and Jakarta review are required" : "Preserve an organization-approved supported 3.x line")
                        : "No Spring Boot version evidence was found",
                bootKnown ? HealthModels.EvidenceStatus.PASS : HealthModels.EvidenceStatus.INCONCLUSIVE, version));
        boolean javax = health.findings().stream().anyMatch(f -> f.code().equals("LEGACY_JAVAX_API"));
        decisions.add(new PlanningModels.CompatibilityDecision("JAKARTA", javax ? "javax" : "not-detected", target.jakartaNamespace(),
                !javax, javax, javax ? "Source evidence contains legacy Java EE namespaces" : "No legacy namespace was detected by static scan",
                HealthModels.EvidenceStatus.PASS, version));
        return decisions;
    }
    private static int major(String version) { try { return Integer.parseInt(version.split("[.-]",2)[0]); } catch (RuntimeException ignored) { return 0; } }
}
