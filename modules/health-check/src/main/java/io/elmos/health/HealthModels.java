package io.elmos.health;

import java.time.Instant;
import java.util.List;
import java.util.Map;

public final class HealthModels {
    private HealthModels() {}

    public enum EvidenceStatus { PASS, FAIL, INCONCLUSIVE, NOT_RUN }
    public enum BuildSystem { MAVEN, GRADLE, MIXED, UNKNOWN }
    public enum Severity { INFO, LOW, MEDIUM, HIGH, CRITICAL }

    public record Module(String path, String groupId, String artifactId, String version,
                         BuildSystem buildSystem, List<String> declaredModules) {
        public Module { declaredModules = List.copyOf(declaredModules); }
        public String coordinate() { return safe(groupId) + ":" + safe(artifactId) + ":" + safe(version); }
    }

    public record Dependency(String groupId, String artifactId, String version, String scope,
                             String modulePath, boolean direct) {
        public String key() { return safe(groupId) + ":" + safe(artifactId); }
        public boolean resolved() { return version != null && !version.isBlank() && !version.contains("${"); }
    }

    public record Vulnerability(String id, String dependency, Severity severity, String summary,
                                String advisoryUrl, String fixedVersion, Instant observedAt) {}

    public record Finding(String code, String category, Severity severity, String location,
                          String message, EvidenceStatus status, Map<String, String> attributes) {
        public Finding { attributes = Map.copyOf(attributes); }
    }

    public record PublicApi(String kind, String owner, String signature, String location) {}

    public record TestReadiness(int productionFiles, int testFiles, boolean junitDetected,
                                boolean integrationTestsDetected, boolean coveragePluginDetected,
                                double testToProductionRatio, EvidenceStatus status) {}

    public record TargetRecommendation(int javaVersion, String springBootLine, String rationale,
                                       EvidenceStatus status, List<String> assumptions) {
        public TargetRecommendation { assumptions = List.copyOf(assumptions); }
    }

    public record VulnerabilityEvidence(EvidenceStatus status, String provider, Instant observedAt,
                                        String databaseVersion, String errorCode) {}

    public record LegacyHealthReport(
            String schemaVersion,
            String reportId,
            String snapshotId,
            Instant generatedAt,
            BuildSystem buildSystem,
            String detectedJavaVersion,
            String springBootVersion,
            String springCloudVersion,
            List<Module> modules,
            List<Dependency> dependencies,
            List<Vulnerability> vulnerabilities,
            VulnerabilityEvidence vulnerabilityEvidence,
            List<Finding> findings,
            List<PublicApi> publicApis,
            TestReadiness testReadiness,
            TargetRecommendation targetRecommendation,
            int healthScore,
            Severity overallRisk,
            EvidenceStatus status,
            List<String> evidenceDigests) {
        public LegacyHealthReport {
            if (!"1.0".equals(schemaVersion)) throw new IllegalArgumentException("unsupported health report schema version");
            modules = List.copyOf(modules); dependencies = List.copyOf(dependencies);
            vulnerabilities = List.copyOf(vulnerabilities); findings = List.copyOf(findings);
            publicApis = List.copyOf(publicApis); evidenceDigests = List.copyOf(evidenceDigests);
        }
    }

    public record VulnerabilityQueryResult(List<Vulnerability> vulnerabilities, VulnerabilityEvidence evidence) {
        public VulnerabilityQueryResult { vulnerabilities = List.copyOf(vulnerabilities); }
    }

    public interface VulnerabilityProvider {
        VulnerabilityQueryResult query(List<Dependency> resolvedDependencies);
    }

    private static String safe(String value) { return value == null ? "" : value; }
}
