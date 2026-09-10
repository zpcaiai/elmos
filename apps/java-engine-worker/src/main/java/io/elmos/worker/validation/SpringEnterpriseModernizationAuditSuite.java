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
 * Enterprise Modernization Audit Suite.
 *
 * <p>Executes all 4 industrial-grade validators against modernized project workspaces:
 * <ol>
 *   <li>{@link SpringSecurityAuditValidator}: SecurityFilterChain, lambda DSL, requestMatchers, method security.</li>
 *   <li>{@link SpringJpaHibernateQueryValidator}: Jakarta Persistence, @JdbcTypeCode(JSON), SQM positional parameters, CriteriaBuilder.</li>
 *   <li>{@link SpringCloudArchitectureValidator}: LoadBalancer, Gateway, Resilience4j, OpenFeign, Micrometer Tracing.</li>
 *   <li>{@link SpringXmlMigrationValidator}: Completeness of XML bean definitions, tx, component-scan to JavaConfig.</li>
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
            double overallMaturityScore,
            boolean fullyCertified,
            List<String> auditLogs
    ) {}

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

    /**
     * Runs comprehensive audit checks on a single modernized project directory.
     */
    public ProjectAuditVerdict auditModernizedProject(Path projectRoot, String projectId, String projectName) throws IOException {
        List<String> logs = new ArrayList<>();
        logs.add("Auditing project: " + projectId + " (" + projectName + ")");

        // 1. Security Audit
        var secReport = securityValidator.auditProject(projectRoot);
        logs.add("  - Security Audit: " + (secReport.isCompliant() ? "COMPLIANT" : "NON-COMPLIANT")
                + " (Score: " + secReport.complianceScore() + ", Violations: " + secReport.totalViolations() + ")");

        // 2. JPA / Hibernate Audit
        var jpaReport = jpaValidator.auditProject(projectRoot);
        logs.add("  - JPA / Hibernate Audit: " + (jpaReport.isCompliant() ? "COMPLIANT" : "NON-COMPLIANT")
                + " (Score: " + jpaReport.complianceScore() + ", Violations: " + jpaReport.totalViolations() + ")");

        // 3. Spring Cloud Audit
        var cloudReport = cloudValidator.auditProject(projectRoot);
        for (var v : cloudReport.violations()) logs.add("    Cloud Violation: " + v.ruleId() + " " + v.filePath() + ":" + v.line() + " - " + v.message()); logs.add("  - Spring Cloud Audit: " + (cloudReport.isCompliant() ? "COMPLIANT" : "NON-COMPLIANT")
                + " (Score: " + cloudReport.complianceScore() + ", Violations: " + cloudReport.totalViolations() + ")");

        // 4. XML Migration Audit
        var xmlReport = xmlValidator.auditProject(projectRoot);
        logs.add("  - XML Migration Audit: " + (xmlReport.isFullyMigrated() ? "COMPLIANT" : "PARTIAL")
                + " (Completeness: " + xmlReport.migrationCompletenessRate() + "%)");

        double overallScore = (secReport.complianceScore() + jpaReport.complianceScore() + cloudReport.complianceScore() + xmlReport.migrationCompletenessRate()) / 4.0;
        boolean certified = secReport.isCompliant() && jpaReport.isCompliant() && cloudReport.isCompliant() && xmlReport.isFullyMigrated();

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
}
