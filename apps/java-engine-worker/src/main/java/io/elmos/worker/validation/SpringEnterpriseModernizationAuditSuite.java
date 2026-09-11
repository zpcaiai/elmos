package io.elmos.worker.validation;

import io.elmos.worker.corpus.SpringThirtyOpenSourceProjectsCorpus;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Enterprise Modernization 7-in-1 Unified Industrial Audit Suite.
 *
 * <p>Executes all 7 industrial-grade validators against modernized project workspaces:
 * <ol>
 *   <li>{@link SpringSecurityAuditValidator}: SecurityFilterChain, lambda DSL, requestMatchers, method security.</li>
 *   <li>{@link SpringJpaHibernateQueryValidator}: Jakarta Persistence, @JdbcTypeCode(JSON), SQM positional parameters, CriteriaBuilder.</li>
 *   <li>{@link SpringCloudArchitectureValidator}: LoadBalancer, Gateway, Resilience4j, OpenFeign, Micrometer Tracing.</li>
 *   <li>{@link SpringXmlMigrationValidator}: Completeness of XML bean definitions, tx, component-scan to JavaConfig.</li>
 *   <li>{@link SpringEcosystemAuditValidator}: Springfox to Springdoc, MyBatis 3.0.3+ Jakarta upgrade, -parameters flag.</li>
 *   <li>{@link SpringWebRoutingAuditValidator}: Trailing-slash URL matching configuration, jakarta.servlet exception handlers.</li>
 *   <li>{@link SpringTestingAuditValidator}: JUnit 4 to JUnit 5 Jupiter migration, assertion integrity, Zero-Test Rule.</li>
 * </ol>
 */
public final class SpringEnterpriseModernizationAuditSuite {

    public record ProjectAuditVerdict(
            String projectId,
            String projectName,
            boolean securityCompliant,
            double securityScore,
            boolean jpaCompliant,
            double jpaScore,
            boolean cloudCompliant,
            double cloudScore,
            boolean xmlCompliant,
            double xmlScore,
            boolean ecosystemCompliant,
            double ecosystemScore,
            boolean webCompliant,
            double webScore,
            boolean testingCompliant,
            double testingScore,
            double overallMaturityScore,
            boolean fullyCertified,
            List<String> auditLogs
    ) {
        public ProjectAuditVerdict(
                String projectId,
                String projectName,
                boolean securityCompliant,
                double securityScore,
                boolean jpaCompliant,
                double jpaScore,
                boolean cloudCompliant,
                double cloudScore,
                boolean xmlCompliant,
                double xmlScore,
                double overallMaturityScore,
                boolean fullyCertified,
                List<String> auditLogs
        ) {
            this(projectId, projectName,
                    securityCompliant, securityScore,
                    jpaCompliant, jpaScore,
                    cloudCompliant, cloudScore,
                    xmlCompliant, xmlScore,
                    true, 100.0,
                    true, 100.0,
                    true, 100.0,
                    overallMaturityScore, fullyCertified, auditLogs);
        }
    }

    public record SuiteAuditReport(
            int totalProjectsAudited,
            int certifiedProjectsCount,
            double certificationRate,
            double averageMaturityScore,
            boolean allProjectsCertified,
            Map<String, ProjectAuditVerdict> projectVerdicts
    ) {}

    private final SpringSecurityAuditValidator securityValidator = new SpringSecurityAuditValidator();
    private final SpringJpaHibernateQueryValidator jpaValidator = new SpringJpaHibernateQueryValidator();
    private final SpringCloudArchitectureValidator cloudValidator = new SpringCloudArchitectureValidator();
    private final SpringXmlMigrationValidator xmlValidator = new SpringXmlMigrationValidator();
    private final SpringEcosystemAuditValidator ecosystemValidator = new SpringEcosystemAuditValidator();
    private final SpringWebRoutingAuditValidator webValidator = new SpringWebRoutingAuditValidator();
    private final SpringTestingAuditValidator testingValidator = new SpringTestingAuditValidator();

    /**
     * Runs comprehensive 7-domain audit checks on a single modernized project directory.
     */
    public ProjectAuditVerdict auditModernizedProject(Path projectRoot, String projectId, String projectName) throws IOException {
        List<String> logs = new ArrayList<>();
        logs.add("Auditing project: " + projectId + " (" + projectName + ")");

        // 1. Security Audit
        var secReport = securityValidator.auditProject(projectRoot);
        for (var v : secReport.violations()) {
            logs.add("    Security Violation: " + v.ruleId() + " " + v.filePath() + ":" + v.line() + " - " + v.message());
        }
        logs.add("  - Security Audit: " + (secReport.isCompliant() ? "COMPLIANT" : "NON-COMPLIANT")
                + " (Score: " + secReport.complianceScore() + ", Violations: " + secReport.totalViolations() + ")");

        // 2. JPA / Hibernate Audit
        var jpaReport = jpaValidator.auditProject(projectRoot);
        for (var v : jpaReport.violations()) {
            logs.add("    JPA Violation: " + v.ruleId() + " " + v.filePath() + ":" + v.line() + " - " + v.message());
        }
        logs.add("  - JPA / Hibernate Audit: " + (jpaReport.isCompliant() ? "COMPLIANT" : "NON-COMPLIANT")
                + " (Score: " + jpaReport.complianceScore() + ", Violations: " + jpaReport.totalViolations() + ")");

        // 3. Spring Cloud Audit
        var cloudReport = cloudValidator.auditProject(projectRoot);
        for (var v : cloudReport.violations()) {
            logs.add("    Cloud Violation: " + v.ruleId() + " " + v.filePath() + ":" + v.line() + " - " + v.message());
        }
        logs.add("  - Spring Cloud Audit: " + (cloudReport.isCompliant() ? "COMPLIANT" : "NON-COMPLIANT")
                + " (Score: " + cloudReport.complianceScore() + ", Violations: " + cloudReport.totalViolations() + ")");

        // 4. XML Migration Audit
        var xmlReport = xmlValidator.auditProject(projectRoot);
        logs.add("  - XML Migration Audit: " + (xmlReport.isFullyMigrated() ? "COMPLIANT" : "PARTIAL")
                + " (Completeness: " + xmlReport.migrationCompletenessRate() + "%)");

        // 5. Ecosystem Audit (Springfox, MyBatis, -parameters)
        var ecoReport = ecosystemValidator.auditProject(projectRoot);
        for (var v : ecoReport.violations()) {
            logs.add("    Ecosystem Violation: " + v.ruleId() + " " + v.filePath() + ":" + v.line() + " - " + v.message());
        }
        logs.add("  - Ecosystem Audit: " + (ecoReport.isCompliant() ? "COMPLIANT" : "NON-COMPLIANT")
                + " (Score: " + ecoReport.complianceScore() + ", Violations: " + ecoReport.totalViolations() + ")");

        // 6. Web Routing Audit (Trailing slash, jakarta exception handlers)
        var webReport = webValidator.auditProject(projectRoot);
        for (var v : webReport.violations()) {
            logs.add("    Web Routing Violation: " + v.ruleId() + " " + v.filePath() + ":" + v.line() + " - " + v.message());
        }
        logs.add("  - Web Routing Audit: " + (webReport.isCompliant() ? "COMPLIANT" : "NON-COMPLIANT")
                + " (Score: " + webReport.complianceScore() + ", Violations: " + webReport.totalViolations() + ")");

        // 7. Testing Suite Audit (JUnit 4 -> 5 Jupiter, Zero-test rule)
        var testReport = testingValidator.auditProject(projectRoot);
        for (var v : testReport.violations()) {
            logs.add("    Testing Violation: " + v.ruleId() + " " + v.filePath() + ":" + v.line() + " - " + v.message());
        }
        logs.add("  - Testing Suite Audit: " + (testReport.isCompliant() ? "COMPLIANT" : "NON-COMPLIANT")
                + " (Score: " + testReport.complianceScore() + ", Violations: " + testReport.totalViolations() + ")");

        double overallScore = (secReport.complianceScore()
                + jpaReport.complianceScore()
                + cloudReport.complianceScore()
                + xmlReport.migrationCompletenessRate()
                + ecoReport.complianceScore()
                + webReport.complianceScore()
                + testReport.complianceScore()) / 7.0;

        boolean certified = secReport.isCompliant()
                && jpaReport.isCompliant()
                && cloudReport.isCompliant()
                && xmlReport.isFullyMigrated()
                && ecoReport.isCompliant()
                && webReport.isCompliant()
                && testReport.isCompliant();

        return new ProjectAuditVerdict(
                projectId,
                projectName,
                secReport.isCompliant(),
                secReport.complianceScore(),
                jpaReport.isCompliant(),
                jpaReport.complianceScore(),
                cloudReport.isCompliant(),
                cloudReport.complianceScore(),
                xmlReport.isFullyMigrated(),
                xmlReport.migrationCompletenessRate(),
                ecoReport.isCompliant(),
                ecoReport.complianceScore(),
                webReport.isCompliant(),
                webReport.complianceScore(),
                testReport.isCompliant(),
                testReport.complianceScore(),
                overallScore,
                certified,
                Collections.unmodifiableList(logs)
        );
    }

    /**
     * Executes the audit suite across all 30 open source projects in the corpus after running the modernization pipeline.
     */
    public SuiteAuditReport auditCorpus(Path workDir) throws IOException {
        List<SpringThirtyOpenSourceProjectsCorpus.ProjectSpec> projects = SpringThirtyOpenSourceProjectsCorpus.getCorpus();
        Map<String, ProjectAuditVerdict> verdicts = new LinkedHashMap<>();
        int certifiedCount = 0;
        double scoreSum = 0.0;

        for (var spec : projects) {
            Path projectRoot = workDir.resolve(spec.id());
            if (!Files.exists(projectRoot)) {
                // Run project modernization first
                SpringThirtyOpenSourceProjectsCorpus.executePipeline(spec, workDir);
            }

            ProjectAuditVerdict verdict = auditModernizedProject(projectRoot, spec.id(), spec.name());
            verdicts.put(spec.id(), verdict);
            if (verdict.fullyCertified()) {
                certifiedCount++;
            }
            scoreSum += verdict.overallMaturityScore();
        }

        int total = projects.size();
        double certRate = total == 0 ? 100.0 : ((double) certifiedCount / total) * 100.0;
        double avgScore = total == 0 ? 100.0 : scoreSum / total;
        boolean allCertified = certifiedCount == total;

        return new SuiteAuditReport(
                total,
                certifiedCount,
                certRate,
                avgScore,
                allCertified,
                Collections.unmodifiableMap(verdicts)
        );
    }

    public record ShimHygieneVerdict(
            boolean isCompliant,
            int totalShimsFound,
            int compliantShimsCount,
            List<String> nonCompliantFiles,
            String summary
    ) {}

    public record ReactorIntegrityVerdict(
            boolean isMultiModule,
            int totalModulesDiscovered,
            boolean allSubmodulesExist,
            List<String> missingSubmodules,
            String summary
    ) {}

    /**
     * Audits hygiene of generated private artifact mock shims.
     * Ensures all generated stubs have @ConditionalOnMissingBean to avoid shadowing real beans.
     */
    public static ShimHygieneVerdict auditShimHygiene(Path projectRoot) {
        if (!Files.isDirectory(projectRoot)) {
            return new ShimHygieneVerdict(true, 0, 0, Collections.emptyList(), "Project root is not a directory");
        }
        int total = 0;
        int compliant = 0;
        List<String> nonCompliant = new ArrayList<>();

        try (var stream = Files.walk(projectRoot)) {
            List<Path> javaFiles = stream.filter(Files::isRegularFile).filter(p -> p.toString().endsWith(".java")).toList();
            for (Path p : javaFiles) {
                String code = Files.readString(p);
                if (code.contains("Automatically synthesized Mock Shim stub by Elmos")) {
                    total++;
                    boolean isServiceOrComponent = code.contains("@Component");
                    if (isServiceOrComponent) {
                        if (code.contains("@ConditionalOnMissingBean")) {
                            compliant++;
                        } else {
                            nonCompliant.add(p.toString());
                        }
                    } else {
                        compliant++; // Interface or DTO does not need @ConditionalOnMissingBean
                    }
                }
            }
        } catch (IOException e) {
            return new ShimHygieneVerdict(false, total, compliant, List.of("IO error: " + e.getMessage()), "Failed to audit shims");
        }

        boolean ok = nonCompliant.isEmpty();
        String summary = total == 0 ? "No synthetic shims present" : "Verified " + compliant + "/" + total + " shims compliant with @ConditionalOnMissingBean hygiene";
        return new ShimHygieneVerdict(ok, total, compliant, Collections.unmodifiableList(nonCompliant), summary);
    }

    /**
     * Audits multi-module reactor topology and parent-child consistency.
     */
    public static ReactorIntegrityVerdict auditReactorIntegrity(Path projectRoot) {
        Path rootPom = projectRoot.resolve("pom.xml");
        if (!Files.isRegularFile(rootPom)) {
            return new ReactorIntegrityVerdict(false, 0, true, Collections.emptyList(), "Single module / no root pom");
        }

        List<String> submodules = io.elmos.worker.SpringMultiModuleProjectScanner.declaredSubmodules(rootPom);
        if (submodules.isEmpty()) {
            return new ReactorIntegrityVerdict(false, 1, true, Collections.emptyList(), "Single module project");
        }

        List<String> missing = new ArrayList<>();
        for (String sub : submodules) {
            Path subPom = projectRoot.resolve(sub).resolve("pom.xml");
            if (!Files.isRegularFile(subPom)) {
                missing.add(sub);
            }
        }

        List<io.elmos.worker.SpringMultiModuleProjectScanner.ReactorModuleNode> dag =
                io.elmos.worker.SpringMultiModuleProjectScanner.resolveReactorDag(projectRoot);

        boolean allExist = missing.isEmpty();
        String summary = "Multi-module reactor verified: " + dag.size() + " modules discovered in DAG. " + (allExist ? "All declared submodules verified." : "Missing: " + missing);
        return new ReactorIntegrityVerdict(true, dag.size(), allExist, Collections.unmodifiableList(missing), summary);
    }

    /**
     * Audits asynchronous messaging stream equivalence.
     */
    public static io.elmos.worker.messaging.SpringAsyncMessagingDifferentialComparator.MessagingEquivalenceVerdict auditAsyncMessagingEquivalence(
            List<io.elmos.worker.messaging.SpringAsyncMessagingDifferentialComparator.MessageEvent> baseline,
            List<io.elmos.worker.messaging.SpringAsyncMessagingDifferentialComparator.MessageEvent> modernized
    ) {
        var comparator = new io.elmos.worker.messaging.SpringAsyncMessagingDifferentialComparator();
        return comparator.compareStreams(baseline, modernized);
    }
}
