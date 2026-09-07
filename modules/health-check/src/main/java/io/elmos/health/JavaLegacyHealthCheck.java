package io.elmos.health;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.time.Clock;
import java.util.*;

public final class JavaLegacyHealthCheck {
    public record Request(String snapshotId, Path projectRoot) {
        public Request {
            if (snapshotId == null || snapshotId.isBlank()) throw new IllegalArgumentException("snapshotId is required");
            Objects.requireNonNull(projectRoot, "projectRoot");
        }
    }

    private final ScanPolicy policy; private final HealthModels.VulnerabilityProvider vulnerabilities; private final Clock clock;

    public JavaLegacyHealthCheck(ScanPolicy policy, HealthModels.VulnerabilityProvider vulnerabilities, Clock clock) {
        this.policy = Objects.requireNonNull(policy); this.vulnerabilities = Objects.requireNonNull(vulnerabilities); this.clock = Objects.requireNonNull(clock);
    }

    public HealthModels.LegacyHealthReport scan(Request request) {
        Objects.requireNonNull(request); Path root = request.projectRoot().toAbsolutePath().normalize();
        BuildInventory inventory = new ProjectDiscovery(policy).discover(root);
        List<HealthModels.Finding> findings = new ArrayList<>(inventory.findings());
        findings.addAll(dependencyConflicts(inventory.dependencies()));
        SourceRiskAnalyzer.Result source = new SourceRiskAnalyzer(policy).analyze(root, inventory);
        findings.addAll(source.findings());
        if (!inventory.dependencies().isEmpty()) findings.add(new HealthModels.Finding("TRANSITIVE_GRAPH_REQUIRES_BUILD_EVIDENCE", "DEPENDENCY",
                HealthModels.Severity.MEDIUM, ".", "Static scan contains declared dependencies; transitive resolution must be attached from an approved build",
                HealthModels.EvidenceStatus.INCONCLUSIVE, Map.of("declaredDependencies", Integer.toString(inventory.dependencies().size()))));

        List<HealthModels.Dependency> resolved = inventory.dependencies().stream().filter(HealthModels.Dependency::resolved).toList();
        HealthModels.VulnerabilityQueryResult vulnerabilityResult;
        try { vulnerabilityResult = vulnerabilities.query(resolved); }
        catch (RuntimeException error) {
            vulnerabilityResult = new HealthModels.VulnerabilityQueryResult(List.of(), new HealthModels.VulnerabilityEvidence(
                    HealthModels.EvidenceStatus.INCONCLUSIVE, "UNAVAILABLE", clock.instant(), null, "VULNERABILITY_QUERY_FAILED"));
        }
        String javaVersion = detectJava(inventory.properties());
        String boot = first(inventory.properties().get("elmos.spring-boot.version"), dependencyVersion(inventory.dependencies(), "org.springframework.boot", "spring-boot"));
        String cloud = first(inventory.properties().get("elmos.spring-cloud.version"), dependencyVersion(inventory.dependencies(), "org.springframework.cloud", "spring-cloud-context"));
        HealthModels.TestReadiness test = testReadiness(inventory);
        HealthModels.TargetRecommendation target = recommend(javaVersion, boot);
        findings.sort(Comparator.comparing(HealthModels.Finding::severity).reversed().thenComparing(HealthModels.Finding::code).thenComparing(HealthModels.Finding::location));
        List<String> digests = evidenceDigests(root, inventory);
        int score = score(findings, vulnerabilityResult.vulnerabilities(), test);
        HealthModels.Severity risk = overallRisk(findings, vulnerabilityResult.vulnerabilities());
        HealthModels.EvidenceStatus status = inventory.buildSystem() == HealthModels.BuildSystem.UNKNOWN
                || vulnerabilityResult.evidence().status() == HealthModels.EvidenceStatus.INCONCLUSIVE
                || findings.stream().anyMatch(f -> f.status() == HealthModels.EvidenceStatus.INCONCLUSIVE)
                ? HealthModels.EvidenceStatus.INCONCLUSIVE
                : risk.ordinal() >= HealthModels.Severity.HIGH.ordinal() ? HealthModels.EvidenceStatus.FAIL : HealthModels.EvidenceStatus.PASS;
        String reportId = "health-" + sha256((request.snapshotId() + "\0" + String.join("\0", digests)).getBytes(StandardCharsets.UTF_8)).substring(0, 24);
        return new HealthModels.LegacyHealthReport("1.0", reportId, request.snapshotId(), clock.instant(), inventory.buildSystem(), javaVersion,
                boot, cloud, inventory.modules(), inventory.dependencies(), vulnerabilityResult.vulnerabilities(), vulnerabilityResult.evidence(),
                findings, source.publicApis(), test, target, score, risk, status, digests);
    }

    private static List<HealthModels.Finding> dependencyConflicts(List<HealthModels.Dependency> dependencies) {
        Map<String, Set<String>> versions = new TreeMap<>();
        for (HealthModels.Dependency dependency : dependencies) if (dependency.resolved()) versions.computeIfAbsent(dependency.key(), ignored -> new TreeSet<>()).add(dependency.version());
        List<HealthModels.Finding> result = new ArrayList<>();
        versions.forEach((key, values) -> { if (values.size() > 1) result.add(new HealthModels.Finding("DEPENDENCY_VERSION_CONFLICT", "DEPENDENCY",
                HealthModels.Severity.HIGH, ".", key + " declares conflicting versions " + values, HealthModels.EvidenceStatus.FAIL,
                Map.of("dependency", key, "versions", String.join(",", values)))); });
        return result;
    }
    private static HealthModels.TestReadiness testReadiness(BuildInventory inventory) {
        int production = inventory.javaFiles().size(), tests = inventory.testFiles().size();
        boolean junit = Boolean.parseBoolean(inventory.properties().getOrDefault("elmos.junit.detected", "false"));
        boolean integration = inventory.testFiles().stream().anyMatch(path -> path.toString().contains("integrationTest") || path.getFileName().toString().endsWith("IT.java"));
        boolean coverage = Boolean.parseBoolean(inventory.properties().getOrDefault("elmos.coverage.detected", "false"));
        double ratio = production == 0 ? 0 : Math.round((tests / (double) production) * 1000d) / 1000d;
        HealthModels.EvidenceStatus status = production == 0 ? HealthModels.EvidenceStatus.INCONCLUSIVE : tests == 0 || !junit ? HealthModels.EvidenceStatus.FAIL : HealthModels.EvidenceStatus.PASS;
        return new HealthModels.TestReadiness(production, tests, junit, integration, coverage, ratio, status);
    }
    private static String detectJava(Map<String, String> properties) {
        String value = first(properties.get("maven.compiler.release"), properties.get("maven.compiler.source"), properties.get("java.version"), properties.get("maven.compiler.target"));
        if (value == null) return null; value = value.strip(); if (value.startsWith("1.")) value = value.substring(2);
        return value.matches("[0-9]{1,2}") ? value : null;
    }
    private static HealthModels.TargetRecommendation recommend(String currentJava, String boot) {
        List<String> assumptions = new ArrayList<>();
        if (currentJava == null) assumptions.add("Current Java level is not declared in build metadata");
        if (boot == null) assumptions.add("Spring Boot version was not identified");
        String line = boot == null ? null : major(boot) < 3 ? "3.x" : "preserve-supported-3.x-line";
        return new HealthModels.TargetRecommendation(21, line,
                "Java 21 is the default ELMOS modernization baseline; Java 17 or 25 requires an explicit organization compatibility profile",
                currentJava == null ? HealthModels.EvidenceStatus.INCONCLUSIVE : HealthModels.EvidenceStatus.PASS, assumptions);
    }
    private static int score(List<HealthModels.Finding> findings, List<HealthModels.Vulnerability> vulnerabilities, HealthModels.TestReadiness test) {
        int score = 100;
        for (HealthModels.Finding finding : findings) score -= finding.status() == HealthModels.EvidenceStatus.INCONCLUSIVE ? 3 : switch (finding.severity()) {
            case CRITICAL -> 25; case HIGH -> 12; case MEDIUM -> 5; case LOW -> 2; case INFO -> 0;
        };
        for (HealthModels.Vulnerability vulnerability : vulnerabilities) score -= switch (vulnerability.severity()) {
            case CRITICAL -> 25; case HIGH -> 12; case MEDIUM -> 5; case LOW -> 2; case INFO -> 0;
        };
        if (test.status() == HealthModels.EvidenceStatus.FAIL) score -= 15;
        return Math.max(0, score);
    }
    private static HealthModels.Severity overallRisk(List<HealthModels.Finding> findings, List<HealthModels.Vulnerability> vulnerabilities) {
        HealthModels.Severity risk = HealthModels.Severity.INFO;
        for (HealthModels.Finding finding : findings) if (finding.status() == HealthModels.EvidenceStatus.FAIL && finding.severity().ordinal() > risk.ordinal()) risk = finding.severity();
        for (HealthModels.Vulnerability vulnerability : vulnerabilities) if (vulnerability.severity().ordinal() > risk.ordinal()) risk = vulnerability.severity();
        return risk;
    }
    private static List<String> evidenceDigests(Path root, BuildInventory inventory) {
        List<Path> files = new ArrayList<>(inventory.buildFiles()); files.addAll(inventory.javaFiles()); files.addAll(inventory.testFiles());
        files.sort(Comparator.comparing(Path::toString)); List<String> result = new ArrayList<>();
        for (Path file : files) try { result.add(root.relativize(file).toString().replace('\\','/') + ":sha256:" + sha256(Files.readAllBytes(file))); }
        catch (Exception error) { throw new IllegalArgumentException("EVIDENCE_DIGEST_FAILED", error); }
        return result;
    }
    private static String dependencyVersion(List<HealthModels.Dependency> dependencies, String group, String artifactPrefix) { return dependencies.stream().filter(d -> group.equals(d.groupId()) && d.artifactId() != null && d.artifactId().startsWith(artifactPrefix) && d.resolved()).map(HealthModels.Dependency::version).findFirst().orElse(null); }
    private static int major(String version) { try { return Integer.parseInt(version.split("[.-]", 2)[0]); } catch (RuntimeException ignored) { return 0; } }
    private static String first(String... values) { for (String value : values) if (value != null && !value.isBlank()) return value; return null; }
    private static String sha256(byte[] bytes) { try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)); } catch (Exception error) { throw new IllegalStateException(error); } }
}
