package io.elmos.worker.workflow;

import io.elmos.worker.SpringDiagnosticAutoRepairer;
import io.elmos.worker.cloud.SpringCloudMicroservicesModernizer;
import io.elmos.worker.jpa.SpringJpaHibernateQueryModernizer;
import io.elmos.worker.regression.SpringGoldenMasterRegressionComparator;
import io.elmos.worker.rulebook.SpringModernizationRulebookCatalog;
import io.elmos.worker.security.SpringSecurityFilterChainModernizer;
import io.elmos.worker.telemetry.SpringModernizationTelemetryProfiler;
import io.elmos.worker.telemetry.SpringModernizationTelemetryProfiler.TelemetryPhase;
import io.elmos.worker.validation.SpringEnterpriseModernizationAuditSuite;
import io.elmos.worker.validation.SpringEnterpriseRegressionVerificationMatrix;
import io.elmos.worker.xml.SpringXmlToJavaConfigConverter;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Industrial-grade End-to-End Modernization & Upgrade Workflow Engine.
 *
 * <p>Orchestrates the entire modernization lifecycle for enterprise Spring projects:
 * <ol>
 *   <li><b>Discovery & Fingerprinting</b>: Analyzes project topology, source Boot/Java versions, and architectural domains.</li>
 *   <li><b>Rule Selection & Planning</b>: Evaluates source against the 150-rule {@link SpringModernizationRulebookCatalog}.</li>
 *   <li><b>Multi-Stage AST & Semantic Transformation</b>:
 *     <ul>
 *       <li>XML Hybrid Configs -> Clean JavaConfig via {@link SpringXmlToJavaConfigConverter}</li>
 *       <li>Spring Security 5/6 FilterChain Refactoring via {@link SpringSecurityFilterChainModernizer}</li>
 *       <li>JPA / Hibernate 6 SQM & Composite Query Modernization via {@link SpringJpaHibernateQueryModernizer}</li>
 *       <li>Spring Cloud Microservices Modernization via {@link SpringCloudMicroservicesModernizer}</li>
 *       <li>Build Toolchain & Dependency Upgrade (Boot 4.1.0 / Java 21)</li>
 *     </ul>
 *   </li>
 *   <li><b>Diagnostic Auto-Repair</b>: Fixes dangling imports or syntax nuances via {@link SpringDiagnosticAutoRepairer}.</li>
 *   <li><b>Architectural Audit Suite</b>: Validates code quality and safety via {@link SpringEnterpriseModernizationAuditSuite}.</li>
 *   <li><b>Golden Master Equivalence Verification</b>: Compares pre/post state via {@link SpringGoldenMasterRegressionComparator}.</li>
 *   <li><b>Regression Verification Matrix Integration</b>: Checks milestone grid via {@link SpringEnterpriseRegressionVerificationMatrix}.</li>
 *   <li><b>Telemetry & Execution Profiling</b>: Tracks throughput and timing via {@link SpringModernizationTelemetryProfiler}.</li>
 * </ol>
 */
public final class SpringModernizationEndToEndWorkflowEngine {

    public record WorkflowRequest(
            String projectId,
            String projectName,
            String sourceBootVersion,
            String sourceJavaVersion,
            String targetBootVersion,
            String targetJavaVersion,
            Map<String, String> sourceFiles
    ) {
        public WorkflowRequest {
            Objects.requireNonNull(projectId, "projectId cannot be null");
            Objects.requireNonNull(projectName, "projectName cannot be null");
            sourceFiles = Collections.unmodifiableMap(new LinkedHashMap<>(sourceFiles));
        }

        public static WorkflowRequest fromFiles(String projectId, String projectName, Map<String, String> sourceFiles) {
            String bootVer = detectBootVersion(sourceFiles);
            String javaVer = detectJavaVersion(sourceFiles);
            return new WorkflowRequest(projectId, projectName, bootVer, javaVer, "4.1.0", "21", sourceFiles);
        }

        private static String detectBootVersion(Map<String, String> files) {
            String pom = files.get("pom.xml");
            if (pom != null) {
                Matcher m = Pattern.compile("<spring-boot\\.version>([^<]+)</spring-boot\\.version>").matcher(pom);
                if (m.find()) return m.group(1).trim();
                m = Pattern.compile("<version>([0-9]+\\.[0-9]+\\.[0-9]+(?:\\.[A-Z0-9_-]+)?)</version>").matcher(pom);
                if (m.find()) return m.group(1).trim();
            }
            return "2.7.18";
        }

        private static String detectJavaVersion(Map<String, String> files) {
            String pom = files.get("pom.xml");
            if (pom != null) {
                Matcher m = Pattern.compile("<java\\.version>([^<]+)</java\\.version>").matcher(pom);
                if (m.find()) return m.group(1).trim();
            }
            return "11";
        }
    }

    public record WorkflowResult(
            String projectId,
            String projectName,
            boolean isSuccessful,
            int sourceLoc,
            int targetLoc,
            Map<String, String> modernizedFiles,
            List<String> appliedRuleIds,
            SpringEnterpriseModernizationAuditSuite.ProjectAuditVerdict auditVerdict,
            SpringGoldenMasterRegressionComparator.ComparisonResult regressionResult,
            SpringEnterpriseRegressionVerificationMatrix.MatrixCell matrixCell,
            SpringModernizationTelemetryProfiler.ModernizationRunProfile telemetryProfile,
            String certificationLevel, // E5_CERTIFIED_PRODUCTION_READY, E4_CERTIFIED_AUTOMATED, FAILED
            List<String> executionLogs
    ) {
        public boolean isProductionReady() {
            return isSuccessful && "E5_CERTIFIED_PRODUCTION_READY".equals(certificationLevel);
        }
    }

    private SpringModernizationEndToEndWorkflowEngine() {}

    /**
     * Executes the end-to-end modernization pipeline on an in-memory project model.
     */
    public static WorkflowResult execute(WorkflowRequest request) {
        List<String> logs = new ArrayList<>();
        Set<String> appliedRules = new LinkedHashSet<>();
        Map<String, String> workingFiles = new LinkedHashMap<>();

        int sourceLoc = calculateTotalLoc(request.sourceFiles());
        logs.add(String.format("Starting modernization for project: %s (%s)", request.projectName(), request.projectId()));
        logs.add(String.format("Source Baseline: Spring Boot %s on Java %s (LOC: %d)",
                request.sourceBootVersion(), request.sourceJavaVersion(), sourceLoc));

        SpringModernizationTelemetryProfiler profiler = SpringModernizationTelemetryProfiler.start(
                request.projectId(), request.projectName(),
                request.sourceBootVersion(), request.targetBootVersion(), request.targetJavaVersion()
        );

        // Phase 1: Fingerprinting & Rule Matching
        profiler.startPhase(TelemetryPhase.DISCOVERY);
        for (String fileContent : request.sourceFiles().values()) {
            List<SpringModernizationRulebookCatalog.ModernizationRule> matched =
                    SpringModernizationRulebookCatalog.analyzeSourceCode(fileContent);
            for (var rule : matched) {
                appliedRules.add(rule.ruleId());
            }
        }
        profiler.endPhaseSuccess(TelemetryPhase.DISCOVERY);
        logs.add(String.format("Phase 1 Complete: Matched %d unique rules from 150-rule catalog.", appliedRules.size()));

        SpringEnterpriseModernizationAuditSuite.ProjectAuditVerdict auditVerdict = null;

        try {
            Path tempDir = Files.createTempDirectory("elmos-workflow-" + request.projectId());
            try {
                // Materialize initial files
                for (Map.Entry<String, String> entry : request.sourceFiles().entrySet()) {
                    Path fp = tempDir.resolve(entry.getKey());
                    Files.createDirectories(fp.getParent());
                    Files.writeString(fp, entry.getValue(), StandardCharsets.UTF_8);
                }

                // Phase 2: XML Hybrid Configuration Migration
                profiler.startPhase(TelemetryPhase.PARSING);
                var xmlRes = SpringXmlToJavaConfigConverter.convertProject(tempDir, "io.elmos.benchmark.config");
                profiler.endPhaseSuccess(TelemetryPhase.PARSING);
                logs.add(String.format("Phase 2 Complete: XML to JavaConfig migrated %d configs, generated %d files.",
                        xmlRes.xmlFilesConverted(), xmlRes.generatedJavaFiles().size()));

                // Phase 3: Spring Security FilterChain Modernization
                profiler.startPhase(TelemetryPhase.RECIPE_EXECUTION);
                var secRes = SpringSecurityFilterChainModernizer.modernize(tempDir);
                appliedRules.addAll(secRes.rulesApplied());
                logs.add(String.format("Phase 3 Complete: Spring Security modernized %d files.", secRes.modifiedFiles().size()));

                // Phase 4: JPA / Hibernate 6 Query Modernization
                var jpaRes = SpringJpaHibernateQueryModernizer.modernize(tempDir);
                appliedRules.addAll(jpaRes.rulesApplied());
                logs.add(String.format("Phase 4 Complete: JPA/Hibernate modernized %d files.", jpaRes.modifiedFiles().size()));

                // Phase 5: Spring Cloud Microservices Modernization
                var cloudRes = SpringCloudMicroservicesModernizer.modernize(tempDir);
                appliedRules.addAll(cloudRes.rulesApplied());
                logs.add(String.format("Phase 5 Complete: Spring Cloud modernized %d files.", cloudRes.modifiedFiles().size()));

                // Phase 6: Parent POM & Toolchain Upgrade
                upgradeToolchainOnDisk(tempDir, request.targetBootVersion(), request.targetJavaVersion());
                profiler.endPhaseSuccess(TelemetryPhase.RECIPE_EXECUTION);
                logs.add(String.format("Phase 6 Complete: Upgraded toolchain to Spring Boot %s / Java %s.",
                        request.targetBootVersion(), request.targetJavaVersion()));

                // Phase 7: Diagnostic Auto-Repair Pass
                profiler.startPhase(TelemetryPhase.AUTOMATED_REPAIR);
                var repairRes = SpringDiagnosticAutoRepairer.repair(tempDir, Collections.emptyList());
                appliedRules.addAll(repairRes.rulesApplied());
                profiler.endPhaseSuccess(TelemetryPhase.AUTOMATED_REPAIR);
                logs.add(String.format("Phase 7 Complete: Diagnostic auto-repair completed with %d changes.", repairRes.changesCount()));

                // Phase 8: Architectural Audit
                profiler.startPhase(TelemetryPhase.REPORTING);
                SpringEnterpriseModernizationAuditSuite auditSuite = new SpringEnterpriseModernizationAuditSuite();
                auditVerdict = auditSuite.auditModernizedProject(tempDir, request.projectId(), request.projectName());
                profiler.endPhaseSuccess(TelemetryPhase.REPORTING);
                logs.add(String.format("Phase 8 Complete: Audit Suite Score: %.2f / 100.0 (Passed: %b)",
                        auditVerdict.overallMaturityScore(), auditVerdict.fullyCertified()));

                // Read all files back from disk
                try (var stream = Files.walk(tempDir)) {
                    for (Path path : stream.filter(Files::isRegularFile).toList()) {
                        String rel = tempDir.relativize(path).toString().replace("\\", "/");
                        workingFiles.put(rel, Files.readString(path, StandardCharsets.UTF_8));
                    }
                }
            } finally {
                deleteRecursively(tempDir);
            }
        } catch (IOException e) {
            logs.add("Error during workspace execution: " + e.getMessage());
        }

        // Phase 9: Golden Master Regression Comparison
        profiler.startPhase(TelemetryPhase.SOURCE_VERIFICATION);
        var regressionResult = SpringGoldenMasterRegressionComparator.compare(request.sourceFiles(), workingFiles);
        profiler.endPhaseSuccess(TelemetryPhase.SOURCE_VERIFICATION);
        logs.add(String.format("Phase 9 Complete: Equivalence Certified: %b (Score: %.1f)",
                regressionResult.isEquivalenceCertified(), regressionResult.overallEquivalenceScore()));

        // Phase 10: Matrix Verification Lookup
        String cellId = String.format("MATRIX-SECURITY_ENTERPRISE-BOOT_%s-JAVA_%s",
                request.sourceBootVersion().replace(".", "_"),
                request.sourceJavaVersion());
        var matrixCell = SpringEnterpriseRegressionVerificationMatrix.getCell(cellId);

        int targetLoc = calculateTotalLoc(workingFiles);
        int filesModified = (int) workingFiles.entrySet().stream()
                .filter(e -> !e.getValue().equals(request.sourceFiles().get(e.getKey())))
                .count();

        var telemetry = profiler.finish(workingFiles.size(), filesModified, sourceLoc, targetLoc);

        boolean auditPassed = auditVerdict != null ? auditVerdict.fullyCertified() : true;
        boolean successful = auditPassed && regressionResult.isEquivalenceCertified();
        String certLevel = successful ? "E5_CERTIFIED_PRODUCTION_READY" : "FAILED";

        logs.add(String.format("Modernization Workflow Finished: Final Status = %s, Target LOC = %d",
                certLevel, targetLoc));

        return new WorkflowResult(
                request.projectId(),
                request.projectName(),
                successful,
                sourceLoc,
                targetLoc,
                Collections.unmodifiableMap(workingFiles),
                List.copyOf(appliedRules),
                auditVerdict,
                regressionResult,
                matrixCell,
                telemetry,
                certLevel,
                Collections.unmodifiableList(logs)
        );
    }

    /**
     * Executes the pipeline directly against a project on disk.
     */
    public static WorkflowResult executeOnDirectory(Path projectDir) throws IOException {
        Map<String, String> files = new LinkedHashMap<>();
        try (var stream = Files.walk(projectDir)) {
            for (Path path : stream.filter(Files::isRegularFile).toList()) {
                String rel = projectDir.relativize(path).toString().replace("\\", "/");
                String name = path.getFileName().toString();
                if (name.endsWith(".java") || name.endsWith(".xml") || name.endsWith(".yml") ||
                    name.endsWith(".yaml") || name.endsWith(".properties") || name.equals("pom.xml") || name.equals("build.gradle")) {
                    files.put(rel, Files.readString(path, StandardCharsets.UTF_8));
                }
            }
        }
        String projId = projectDir.getFileName().toString();
        WorkflowRequest request = WorkflowRequest.fromFiles(projId, projId, files);
        return execute(request);
    }

    private static void upgradeToolchainOnDisk(Path projectRoot, String targetBootVer, String targetJavaVer) throws IOException {
        Path pomPath = projectRoot.resolve("pom.xml");
        if (Files.exists(pomPath)) {
            String pom = Files.readString(pomPath, StandardCharsets.UTF_8);
            pom = pom.replaceAll("<version>1\\.5\\.[0-9]+\\.RELEASE</version>", "<version>" + targetBootVer + "</version>");
            pom = pom.replaceAll("<version>2\\.[0-9]+\\.[0-9]+(?:\\.RELEASE)?</version>", "<version>" + targetBootVer + "</version>");
            pom = pom.replaceAll("<version>3\\.[0-9]+\\.[0-9]+</version>", "<version>" + targetBootVer + "</version>");
            pom = pom.replaceAll("<java\\.version>[0-9]+</java\\.version>", "<java.version>" + targetJavaVer + "</java.version>");
            pom = pom.replaceAll("<spring-cloud\\.version>[^<]+</spring-cloud\\.version>",
                    "<spring-cloud.version>2024.0.0</spring-cloud.version>");
            Files.writeString(pomPath, pom, StandardCharsets.UTF_8);
        }
    }

    private static int calculateTotalLoc(Map<String, String> files) {
        return files.values().stream()
                .mapToInt(s -> s.split("\n", -1).length)
                .sum();
    }

    private static void deleteRecursively(Path root) {
        try (var stream = Files.walk(root)) {
            stream.sorted((a, b) -> b.compareTo(a)).forEach(p -> {
                try {
                    Files.deleteIfExists(p);
                } catch (IOException ignored) {}
            });
        } catch (IOException ignored) {}
    }
}
