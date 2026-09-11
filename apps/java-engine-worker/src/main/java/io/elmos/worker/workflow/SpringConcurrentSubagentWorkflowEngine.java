package io.elmos.worker.workflow;

import io.elmos.worker.SpringDiagnosticAutoRepairer;
import io.elmos.worker.cloud.SpringCloudMicroservicesModernizer;
import io.elmos.worker.ecosystem.SpringEcosystemDependencyModernizer;
import io.elmos.worker.jpa.SpringJpaHibernateQueryModernizer;
import io.elmos.worker.regression.SpringGoldenMasterRegressionComparator;
import io.elmos.worker.regression.SpringGoldenMasterRegressionComparator.ComparisonResult;
import io.elmos.worker.security.SpringSecurityCorsCsrfAdvancedModernizer;
import io.elmos.worker.security.SpringSecurityFilterChainModernizer;
import io.elmos.worker.testing.SpringJUnitModernizer;
import io.elmos.worker.validation.SpringCloudArchitectureValidator;
import io.elmos.worker.validation.SpringEcosystemAuditValidator;
import io.elmos.worker.validation.SpringEnterpriseModernizationAuditSuite;
import io.elmos.worker.validation.SpringEnterpriseModernizationAuditSuite.ProjectAuditVerdict;
import io.elmos.worker.validation.SpringJpaHibernateQueryValidator;
import io.elmos.worker.validation.SpringSecurityAuditValidator;
import io.elmos.worker.validation.SpringTestingAuditValidator;
import io.elmos.worker.validation.SpringWebRoutingAuditValidator;
import io.elmos.worker.validation.SpringXmlMigrationValidator;
import io.elmos.worker.web.SpringMvcWebRoutingModernizer;
import io.elmos.worker.xml.SpringXmlToJavaConfigConverter;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Concurrent 7-Subagent Full Modernization Engine.
 *
 * <p>Orchestrates all 7 industrial modernization subagents concurrently across physical worktree sandboxes:
 * <ol>
 *   <li><b>Subagent A (Security Domain - 25%)</b>: WebSecurityConfigurerAdapter, Lambda DSL, CORS/CSRF, BREACH.</li>
 *   <li><b>Subagent B (Persistence Domain - 20%)</b>: Jakarta Persistence, Hibernate 6 SQM, Criteria AST, ?1 params.</li>
 *   <li><b>Subagent C (Configuration Domain - 15%)</b>: XML DAG topological compilation to modern JavaConfig.</li>
 *   <li><b>Subagent D (Microservices Domain - 15%)</b>: Netflix OSS to Spring Cloud 2023+ (Gateway, LoadBalancer, Resilience4j).</li>
 *   <li><b>Subagent E (Ecosystem Domain - 10%)</b>: Swagger 2 to OpenAPI 3 (Springdoc), MyBatis 3, -parameters compiler flag.</li>
 *   <li><b>Subagent F (Web Routing Domain - 8%)</b>: PathPattern trailing slash compatibility, ProblemDetail RFC 7807.</li>
 *   <li><b>Subagent G (Test Suite Domain - 7%)</b>: JUnit 4 to JUnit 5 Jupiter, Assertions & Runner modernization.</li>
 * </ol>
 */
public final class SpringConcurrentSubagentWorkflowEngine {

    public enum SubagentDomain {
        SECURITY("Subagent-A (Security Domain - 25%)"),
        PERSISTENCE("Subagent-B (Persistence/JPA Domain - 20%)"),
        CONFIGURATION("Subagent-C (Configuration/XML Domain - 15%)"),
        MICROSERVICES("Subagent-D (Microservices/Cloud Domain - 15%)"),
        ECOSYSTEM("Subagent-E (Ecosystem Dependencies - 10%)"),
        WEB_ROUTING("Subagent-F (Spring MVC Web Routing - 8%)"),
        TESTING("Subagent-G (Automated Test Suite - 7%)");

        private final String displayName;

        SubagentDomain(String displayName) {
            this.displayName = displayName;
        }

        public String getDisplayName() {
            return displayName;
        }
    }

    public record SubagentOutcome(
            SubagentDomain domain,
            boolean successful,
            int changesCount,
            Set<String> modifiedFiles,
            List<String> rulesApplied,
            double domainAuditScore,
            boolean domainCompliant,
            long executionDurationMs,
            List<String> executionLogs
    ) {}

    public record ConcurrentWorkflowResult(
            String projectId,
            String projectName,
            boolean isSuccessful,
            boolean isProductionReady,
            String certificationLevel,
            long totalWallClockDurationMs,
            Map<SubagentDomain, SubagentOutcome> subagentOutcomes,
            boolean zeroCollisionInvariantHeld,
            Set<String> collisionsDetected,
            Map<String, String> modernizedFiles,
            List<String> aggregatedRulesApplied,
            ProjectAuditVerdict finalAuditVerdict,
            ComparisonResult regressionResult,
            List<String> orchestratorLogs
    ) {}

    private SpringConcurrentSubagentWorkflowEngine() {}

    /**
     * Executes the full 7-subagent modernization pipeline in parallel with isolated worktrees.
     */
    public static ConcurrentWorkflowResult execute(SpringModernizationEndToEndWorkflowEngine.WorkflowRequest request) {
        Instant startTime = Instant.now();
        List<String> logs = Collections.synchronizedList(new ArrayList<>());
        logs.add(String.format("Starting Concurrent 7-Subagent Full Modernization for %s (%s)", request.projectName(), request.projectId()));

        Path masterWorkspace = null;
        ExecutorService executor = Executors.newFixedThreadPool(7);

        try {
            masterWorkspace = Files.createTempDirectory("elmos-concurrent-master-" + request.projectId());
            // Materialize baseline source files into master workspace
            for (Map.Entry<String, String> entry : request.sourceFiles().entrySet()) {
                Path target = masterWorkspace.resolve(entry.getKey());
                Files.createDirectories(target.getParent());
                Files.writeString(target, entry.getValue(), StandardCharsets.UTF_8);
            }

            // Create isolated worktrees for all 7 subagents
            Path worktreeSec = Files.createTempDirectory("worktree-sec-" + request.projectId());
            Path worktreeJpa = Files.createTempDirectory("worktree-jpa-" + request.projectId());
            Path worktreeXml = Files.createTempDirectory("worktree-xml-" + request.projectId());
            Path worktreeCloud = Files.createTempDirectory("worktree-cloud-" + request.projectId());
            Path worktreeEco = Files.createTempDirectory("worktree-eco-" + request.projectId());
            Path worktreeWeb = Files.createTempDirectory("worktree-web-" + request.projectId());
            Path worktreeTest = Files.createTempDirectory("worktree-test-" + request.projectId());

            copyDirectory(masterWorkspace, worktreeSec);
            copyDirectory(masterWorkspace, worktreeJpa);
            copyDirectory(masterWorkspace, worktreeXml);
            copyDirectory(masterWorkspace, worktreeCloud);
            copyDirectory(masterWorkspace, worktreeEco);
            copyDirectory(masterWorkspace, worktreeWeb);
            copyDirectory(masterWorkspace, worktreeTest);

            // Dispatch all 7 Subagents concurrently
            CompletableFuture<SubagentOutcome> taskA = CompletableFuture.supplyAsync(
                    () -> runSecuritySubagent(worktreeSec), executor);
            CompletableFuture<SubagentOutcome> taskB = CompletableFuture.supplyAsync(
                    () -> runJpaSubagent(worktreeJpa), executor);
            CompletableFuture<SubagentOutcome> taskC = CompletableFuture.supplyAsync(
                    () -> runXmlSubagent(worktreeXml), executor);
            CompletableFuture<SubagentOutcome> taskD = CompletableFuture.supplyAsync(
                    () -> runCloudSubagent(worktreeCloud), executor);
            CompletableFuture<SubagentOutcome> taskE = CompletableFuture.supplyAsync(
                    () -> runEcosystemSubagent(worktreeEco), executor);
            CompletableFuture<SubagentOutcome> taskF = CompletableFuture.supplyAsync(
                    () -> runWebSubagent(worktreeWeb), executor);
            CompletableFuture<SubagentOutcome> taskG = CompletableFuture.supplyAsync(
                    () -> runTestSubagent(worktreeTest), executor);

            // Wait for all 7 Subagents to complete
            CompletableFuture.allOf(taskA, taskB, taskC, taskD, taskE, taskF, taskG).join();

            SubagentOutcome outcomeA = taskA.join();
            SubagentOutcome outcomeB = taskB.join();
            SubagentOutcome outcomeC = taskC.join();
            SubagentOutcome outcomeD = taskD.join();
            SubagentOutcome outcomeE = taskE.join();
            SubagentOutcome outcomeF = taskF.join();
            SubagentOutcome outcomeG = taskG.join();

            Map<SubagentDomain, SubagentOutcome> outcomes = new LinkedHashMap<>();
            outcomes.put(SubagentDomain.SECURITY, outcomeA);
            outcomes.put(SubagentDomain.PERSISTENCE, outcomeB);
            outcomes.put(SubagentDomain.CONFIGURATION, outcomeC);
            outcomes.put(SubagentDomain.MICROSERVICES, outcomeD);
            outcomes.put(SubagentDomain.ECOSYSTEM, outcomeE);
            outcomes.put(SubagentDomain.WEB_ROUTING, outcomeF);
            outcomes.put(SubagentDomain.TESTING, outcomeG);

            logs.add("All 7 subagents completed execution in parallel.");

            // Verify Zero File-Overlap Invariant across all 7 outcomes
            Set<String> collisions = detectCollisions(outcomeA, outcomeB, outcomeC, outcomeD, outcomeE, outcomeF, outcomeG);
            boolean zeroCollisionInvariantHeld = collisions.isEmpty();
            if (!zeroCollisionInvariantHeld) {
                logs.add("CRITICAL CONCURRENCY VIOLATION: Collisions detected across subagents: " + collisions);
            } else {
                logs.add("Zero-Overlap Invariant VERIFIED: All 7 subagent file modification sets are strictly disjoint.");
            }

            // Three-Way Merge: apply subagent outputs to master workspace
            mergeWorktreeChanges(masterWorkspace, worktreeSec, outcomeA.modifiedFiles());
            mergeWorktreeChanges(masterWorkspace, worktreeJpa, outcomeB.modifiedFiles());
            mergeWorktreeChanges(masterWorkspace, worktreeXml, outcomeC.modifiedFiles());
            mergeWorktreeChanges(masterWorkspace, worktreeCloud, outcomeD.modifiedFiles());
            mergeWorktreeChanges(masterWorkspace, worktreeEco, outcomeE.modifiedFiles());
            mergeWorktreeChanges(masterWorkspace, worktreeWeb, outcomeF.modifiedFiles());
            mergeWorktreeChanges(masterWorkspace, worktreeTest, outcomeG.modifiedFiles());

            // Clean up temporary worktrees
            deleteRecursively(worktreeSec);
            deleteRecursively(worktreeJpa);
            deleteRecursively(worktreeXml);
            deleteRecursively(worktreeCloud);
            deleteRecursively(worktreeEco);
            deleteRecursively(worktreeWeb);
            deleteRecursively(worktreeTest);

            // Global Phase: Parent POM & Toolchain Upgrade (Boot 4.1.0 / Java 21)
            upgradeToolchainOnDisk(masterWorkspace, request.targetBootVersion(), request.targetJavaVersion());
            logs.add(String.format("Global toolchain upgraded to Spring Boot %s / Java %s",
                    request.targetBootVersion(), request.targetJavaVersion()));

            // Global Phase: Diagnostic Auto-Repair Pass
            var repairRes = SpringDiagnosticAutoRepairer.repair(masterWorkspace, Collections.emptyList());
            logs.add(String.format("Global Auto-repair completed with %d syntax/import repairs.", repairRes.changesCount()));

            // Global Phase: 4-in-1 Unified Audit Suite
            SpringEnterpriseModernizationAuditSuite auditSuite = new SpringEnterpriseModernizationAuditSuite();
            ProjectAuditVerdict finalAuditVerdict = auditSuite.auditModernizedProject(
                    masterWorkspace, request.projectId(), request.projectName());
            logs.add(String.format("Final Unified Audit Score: %.2f / 100.0 (Certified: %b)",
                    finalAuditVerdict.overallMaturityScore(), finalAuditVerdict.fullyCertified()));

            // Collect working files
            Map<String, String> modernizedFiles = new LinkedHashMap<>();
            try (var stream = Files.walk(masterWorkspace)) {
                for (Path p : stream.filter(Files::isRegularFile).toList()) {
                    String rel = masterWorkspace.relativize(p).toString().replace("\\", "/");
                    modernizedFiles.put(rel, Files.readString(p, StandardCharsets.UTF_8));
                }
            }

            // Global Phase: Golden Master Equivalence Verification
            ComparisonResult regressionResult = SpringGoldenMasterRegressionComparator.compare(
                    request.sourceFiles(), modernizedFiles);
            logs.add(String.format("Golden Master Equivalence Score: %.1f / 100.0 (Certified: %b)",
                    regressionResult.overallEquivalenceScore(), regressionResult.isEquivalenceCertified()));

            // Collect aggregated rules
            Set<String> aggregatedRules = new LinkedHashSet<>();
            for (SubagentOutcome out : outcomes.values()) {
                aggregatedRules.addAll(out.rulesApplied());
            }
            aggregatedRules.addAll(repairRes.rulesApplied());

            long totalDuration = Duration.between(startTime, Instant.now()).toMillis();
            boolean allSubagentsPassed = outcomes.values().stream().allMatch(SubagentOutcome::successful);
            boolean isSuccessful = zeroCollisionInvariantHeld
                    && allSubagentsPassed
                    && finalAuditVerdict.fullyCertified() && regressionResult.isEquivalenceCertified();

            String certLevel = isSuccessful ? "E5_CERTIFIED_PRODUCTION_READY" : "FAILED";
            logs.add(String.format("Concurrent 7-Subagent Modernization Complete: Level = %s in %d ms", certLevel, totalDuration));

            return new ConcurrentWorkflowResult(
                    request.projectId(),
                    request.projectName(),
                    isSuccessful,
                    isSuccessful,
                    certLevel,
                    totalDuration,
                    outcomes,
                    zeroCollisionInvariantHeld,
                    collisions,
                    Collections.unmodifiableMap(modernizedFiles),
                    List.copyOf(aggregatedRules),
                    finalAuditVerdict,
                    regressionResult,
                    Collections.unmodifiableList(logs)
            );

        } catch (Exception e) {
            logs.add("Exception in concurrent 7-subagent workflow: " + e.getMessage());
            return new ConcurrentWorkflowResult(
                    request.projectId(), request.projectName(), false, false, "FAILED",
                    Duration.between(startTime, Instant.now()).toMillis(),
                    Collections.emptyMap(), false, Collections.emptySet(), Collections.emptyMap(),
                    Collections.emptyList(), null, null, Collections.unmodifiableList(logs)
            );
        } finally {
            executor.shutdown();
            if (masterWorkspace != null) {
                deleteRecursively(masterWorkspace);
            }
        }
    }

    private static SubagentOutcome runSecuritySubagent(Path worktree) {
        long start = System.currentTimeMillis();
        List<String> logs = new ArrayList<>();
        logs.add("Subagent-A (Security) started on worktree: " + worktree);
        try {
            var filterChainRes = SpringSecurityFilterChainModernizer.modernize(worktree);
            var corsCsrfRes = SpringSecurityCorsCsrfAdvancedModernizer.modernize(worktree);

            Set<String> modified = new LinkedHashSet<>(filterChainRes.modifiedFiles());
            modified.addAll(corsCsrfRes.modifiedFiles());

            List<String> rules = new ArrayList<>(filterChainRes.rulesApplied());
            rules.addAll(corsCsrfRes.rulesApplied());

            SpringSecurityAuditValidator validator = new SpringSecurityAuditValidator();
            var auditReport = validator.auditProject(worktree);

            return new SubagentOutcome(
                    SubagentDomain.SECURITY,
                    auditReport.isCompliant(),
                    filterChainRes.changesCount() + corsCsrfRes.changesCount(),
                    modified,
                    rules,
                    auditReport.complianceScore(),
                    auditReport.isCompliant(),
                    System.currentTimeMillis() - start,
                    logs
            );
        } catch (Exception e) {
            logs.add("Subagent-A failed: " + e.getMessage());
            return new SubagentOutcome(SubagentDomain.SECURITY, false, 0, Collections.emptySet(),
                    Collections.emptyList(), 0.0, false, System.currentTimeMillis() - start, logs);
        }
    }

    private static SubagentOutcome runJpaSubagent(Path worktree) {
        long start = System.currentTimeMillis();
        List<String> logs = new ArrayList<>();
        logs.add("Subagent-B (JPA) started on worktree: " + worktree);
        try {
            var jpaRes = SpringJpaHibernateQueryModernizer.modernize(worktree);
            SpringJpaHibernateQueryValidator validator = new SpringJpaHibernateQueryValidator();
            var auditReport = validator.auditProject(worktree);

            return new SubagentOutcome(
                    SubagentDomain.PERSISTENCE,
                    auditReport.isCompliant(),
                    jpaRes.changesCount(),
                    jpaRes.modifiedFiles(),
                    jpaRes.rulesApplied(),
                    auditReport.complianceScore(),
                    auditReport.isCompliant(),
                    System.currentTimeMillis() - start,
                    logs
            );
        } catch (Exception e) {
            logs.add("Subagent-B failed: " + e.getMessage());
            return new SubagentOutcome(SubagentDomain.PERSISTENCE, false, 0, Collections.emptySet(),
                    Collections.emptyList(), 0.0, false, System.currentTimeMillis() - start, logs);
        }
    }

    private static SubagentOutcome runXmlSubagent(Path worktree) {
        long start = System.currentTimeMillis();
        List<String> logs = new ArrayList<>();
        logs.add("Subagent-C (XML) started on worktree: " + worktree);
        try {
            var xmlRes = SpringXmlToJavaConfigConverter.convertProject(worktree, "io.elmos.benchmark.config");
            Set<String> modified = new LinkedHashSet<>(xmlRes.generatedJavaFiles());
            List<String> rules = List.of("RULE-SPRING-XML-TO-JAVACONFIG");

            SpringXmlMigrationValidator validator = new SpringXmlMigrationValidator();
            var auditReport = validator.auditProject(worktree);

            return new SubagentOutcome(
                    SubagentDomain.CONFIGURATION,
                    auditReport.isFullyMigrated(),
                    xmlRes.xmlFilesConverted(),
                    modified,
                    rules,
                    auditReport.migrationCompletenessRate(),
                    auditReport.isFullyMigrated(),
                    System.currentTimeMillis() - start,
                    logs
            );
        } catch (Exception e) {
            logs.add("Subagent-C failed: " + e.getMessage());
            return new SubagentOutcome(SubagentDomain.CONFIGURATION, false, 0, Collections.emptySet(),
                    Collections.emptyList(), 0.0, false, System.currentTimeMillis() - start, logs);
        }
    }

    private static SubagentOutcome runCloudSubagent(Path worktree) {
        long start = System.currentTimeMillis();
        List<String> logs = new ArrayList<>();
        logs.add("Subagent-D (Cloud) started on worktree: " + worktree);
        try {
            var cloudRes = SpringCloudMicroservicesModernizer.modernize(worktree);
            SpringCloudArchitectureValidator validator = new SpringCloudArchitectureValidator();
            var auditReport = validator.auditProject(worktree);

            return new SubagentOutcome(
                    SubagentDomain.MICROSERVICES,
                    auditReport.isCompliant(),
                    cloudRes.changesCount(),
                    cloudRes.modifiedFiles(),
                    cloudRes.rulesApplied(),
                    auditReport.complianceScore(),
                    auditReport.isCompliant(),
                    System.currentTimeMillis() - start,
                    logs
            );
        } catch (Exception e) {
            logs.add("Subagent-D failed: " + e.getMessage());
            return new SubagentOutcome(SubagentDomain.MICROSERVICES, false, 0, Collections.emptySet(),
                    Collections.emptyList(), 0.0, false, System.currentTimeMillis() - start, logs);
        }
    }

    private static SubagentOutcome runEcosystemSubagent(Path worktree) {
        long start = System.currentTimeMillis();
        List<String> logs = new ArrayList<>();
        logs.add("Subagent-E (Ecosystem) started on worktree: " + worktree);
        try {
            var ecoRes = SpringEcosystemDependencyModernizer.modernize(worktree);
            logs.add(String.format("Subagent-E finished: %d files modified.", ecoRes.modifiedFiles().size()));

            SpringEcosystemAuditValidator validator = new SpringEcosystemAuditValidator();
            var auditReport = validator.auditProject(worktree);

            return new SubagentOutcome(
                    SubagentDomain.ECOSYSTEM,
                    auditReport.isCompliant(),
                    ecoRes.changesCount(),
                    ecoRes.modifiedFiles(),
                    ecoRes.rulesApplied(),
                    auditReport.complianceScore(),
                    auditReport.isCompliant(),
                    System.currentTimeMillis() - start,
                    logs
            );
        } catch (Exception e) {
            logs.add("Subagent-E failed: " + e.getMessage());
            return new SubagentOutcome(SubagentDomain.ECOSYSTEM, false, 0, Collections.emptySet(),
                    Collections.emptyList(), 0.0, false, System.currentTimeMillis() - start, logs);
        }
    }

    private static SubagentOutcome runWebSubagent(Path worktree) {
        long start = System.currentTimeMillis();
        List<String> logs = new ArrayList<>();
        logs.add("Subagent-F (Web Routing) started on worktree: " + worktree);
        try {
            var webRes = SpringMvcWebRoutingModernizer.modernize(worktree, "io.elmos.benchmark.config");
            logs.add(String.format("Subagent-F finished: %d files modified.", webRes.modifiedFiles().size()));

            SpringWebRoutingAuditValidator validator = new SpringWebRoutingAuditValidator();
            var auditReport = validator.auditProject(worktree);

            return new SubagentOutcome(
                    SubagentDomain.WEB_ROUTING,
                    auditReport.isCompliant(),
                    webRes.changesCount(),
                    webRes.modifiedFiles(),
                    webRes.rulesApplied(),
                    auditReport.complianceScore(),
                    auditReport.isCompliant(),
                    System.currentTimeMillis() - start,
                    logs
            );
        } catch (Exception e) {
            logs.add("Subagent-F failed: " + e.getMessage());
            return new SubagentOutcome(SubagentDomain.WEB_ROUTING, false, 0, Collections.emptySet(),
                    Collections.emptyList(), 0.0, false, System.currentTimeMillis() - start, logs);
        }
    }

    private static SubagentOutcome runTestSubagent(Path worktree) {
        long start = System.currentTimeMillis();
        List<String> logs = new ArrayList<>();
        logs.add("Subagent-G (Test Suite) started on worktree: " + worktree);
        try {
            var testRes = SpringJUnitModernizer.modernize(worktree);
            logs.add(String.format("Subagent-G finished: %d files modified.", testRes.modifiedFiles().size()));

            SpringTestingAuditValidator validator = new SpringTestingAuditValidator();
            var auditReport = validator.auditProject(worktree);

            return new SubagentOutcome(
                    SubagentDomain.TESTING,
                    auditReport.isCompliant(),
                    testRes.changesCount(),
                    testRes.modifiedFiles(),
                    testRes.rulesApplied(),
                    auditReport.complianceScore(),
                    auditReport.isCompliant(),
                    System.currentTimeMillis() - start,
                    logs
            );
        } catch (Exception e) {
            logs.add("Subagent-G failed: " + e.getMessage());
            return new SubagentOutcome(SubagentDomain.TESTING, false, 0, Collections.emptySet(),
                    Collections.emptyList(), 0.0, false, System.currentTimeMillis() - start, logs);
        }
    }

    private static Set<String> detectCollisions(SubagentOutcome... outcomes) {
        Set<String> collisions = new LinkedHashSet<>();
        List<Set<String>> sets = Arrays.stream(outcomes).map(SubagentOutcome::modifiedFiles).toList();
        for (int i = 0; i < sets.size(); i++) {
            for (int j = i + 1; j < sets.size(); j++) {
                Set<String> intersect = new HashSet<>(sets.get(i));
                intersect.retainAll(sets.get(j));
                collisions.addAll(intersect);
            }
        }
        return collisions;
    }

    private static void mergeWorktreeChanges(Path master, Path worktree, Set<String> changedFiles) throws IOException {
        for (String file : changedFiles) {
            Path src = worktree.resolve(file);
            Path dest = master.resolve(file);
            if (Files.exists(src)) {
                Files.createDirectories(dest.getParent());
                Files.copy(src, dest, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
            }
        }
    }

    private static void copyDirectory(Path source, Path target) throws IOException {
        try (var stream = Files.walk(source)) {
            for (Path p : stream.toList()) {
                Path rel = source.relativize(p);
                Path dest = target.resolve(rel);
                if (Files.isDirectory(p)) {
                    Files.createDirectories(dest);
                } else {
                    Files.createDirectories(dest.getParent());
                    Files.copy(p, dest, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
                }
            }
        }
    }

    private static void upgradeToolchainOnDisk(Path projectRoot, String targetBootVer, String targetJavaVer) throws IOException {
        Path pomPath = projectRoot.resolve("pom.xml");
        if (Files.exists(pomPath)) {
            String pom = Files.readString(pomPath, StandardCharsets.UTF_8);
            pom = pom.replaceAll(
                    "(?s)(<artifactId>spring-boot-starter-parent</artifactId>.*?<version>)[^<]+(</version>)",
                    "$1" + targetBootVer + "$2"
            );
            pom = pom.replaceAll(
                    "(?s)(<artifactId>spring-boot-maven-plugin</artifactId>.*?<version>)[^<]+(</version>)",
                    "$1" + targetBootVer + "$2"
            );
            pom = pom.replaceAll("<java\\.version>[0-9]+</java\\.version>", "<java.version>" + targetJavaVer + "</java.version>");
            pom = pom.replaceAll("<spring-cloud\\.version>[^<]+</spring-cloud\\.version>",
                    "<spring-cloud.version>2024.0.0</spring-cloud.version>");
            Files.writeString(pomPath, pom, StandardCharsets.UTF_8);
        }
    }

    private static void deleteRecursively(Path root) {
        if (root == null || !Files.exists(root)) return;
        try (var stream = Files.walk(root)) {
            stream.sorted((a, b) -> b.compareTo(a)).forEach(p -> {
                try {
                    Files.deleteIfExists(p);
                } catch (IOException ignored) {}
            });
        } catch (IOException ignored) {}
    }
}
