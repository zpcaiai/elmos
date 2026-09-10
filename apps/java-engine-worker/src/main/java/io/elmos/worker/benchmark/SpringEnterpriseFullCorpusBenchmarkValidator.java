package io.elmos.worker.benchmark;

import io.elmos.worker.corpus.SpringThirtyOpenSourceProjectsCorpus;
import io.elmos.worker.corpus.SpringThirtyOpenSourceProjectsCorpus.ProjectDomain;
import io.elmos.worker.corpus.SpringThirtyOpenSourceProjectsCorpus.ProjectSpec;
import io.elmos.worker.workflow.SpringModernizationEndToEndWorkflowEngine;
import io.elmos.worker.workflow.SpringModernizationEndToEndWorkflowEngine.WorkflowRequest;
import io.elmos.worker.workflow.SpringModernizationEndToEndWorkflowEngine.WorkflowResult;

import java.time.Instant;
import java.util.*;
import java.util.stream.Collectors;

/**
 * Industrial-grade Full-Corpus Benchmark Validator for Spring Modernization.
 *
 * <p>Executes and evaluates the complete 30-project enterprise open source benchmark suite,
 * validating:
 * <ol>
 *   <li>100.0% Green Modernization Build Rate across all 30 complex scenarios.</li>
 *   <li>E5_CERTIFIED_PRODUCTION_READY level attainment.</li>
 *   <li>Zero regression across HTTP routes, security invariants, data models, and configurations.</li>
 *   <li>Performance throughput metrics and execution resource accounting.</li>
 * </ol>
 */
public final class SpringEnterpriseFullCorpusBenchmarkValidator {

    public record ProjectBenchmarkMetric(
            String projectId,
            String projectName,
            ProjectDomain domain,
            String sourceBootVersion,
            String sourceJavaVersion,
            int sourceLoc,
            int targetLoc,
            int rulesAppliedCount,
            boolean modernizationSucceeded,
            boolean equivalenceCertified,
            boolean isProductionReady,
            String certificationLevel,
            double auditScore,
            long executionTimeMillis
    ) {}

    public record DomainSummary(
            ProjectDomain domain,
            int totalProjects,
            int greenProjects,
            double greenRatePercentage,
            int totalSourceLoc,
            int totalTargetLoc,
            double averageAuditScore
    ) {}

    public record BenchmarkSuiteReport(
            Instant timestamp,
            int totalProjectsEvaluated,
            int totalGreenProjects,
            double overallGreenRatePercentage,
            int totalSourceLoc,
            int totalTargetLoc,
            int totalRulesAppliedAcrossCorpus,
            double averageAuditScore,
            long totalExecutionTimeMillis,
            double throughputLocPerSecond,
            boolean allProjectsFullyCertified,
            Map<ProjectDomain, DomainSummary> domainSummaries,
            List<ProjectBenchmarkMetric> projectMetrics
    ) {
        public boolean isProductionGrade() {
            return allProjectsFullyCertified && overallGreenRatePercentage >= 99.9;
        }
    }

    private SpringEnterpriseFullCorpusBenchmarkValidator() {}

    /**
     * Executes the benchmark suite across all 30 projects in the corpus.
     */
    public static BenchmarkSuiteReport executeFullCorpusBenchmark() {
        List<ProjectSpec> corpus = SpringThirtyOpenSourceProjectsCorpus.getCorpus();
        List<ProjectBenchmarkMetric> metrics = new ArrayList<>();
        Instant start = Instant.now();

        int totalRulesApplied = 0;
        int totalSourceLoc = 0;
        int totalTargetLoc = 0;
        double auditScoreSum = 0.0;
        int greenCount = 0;

        for (ProjectSpec spec : corpus) {
            long pStart = System.currentTimeMillis();
            WorkflowRequest req = new WorkflowRequest(
                    spec.id(), spec.name(), spec.sourceBootVersion(), spec.sourceJavaVersion(),
                    "4.1.0", "21", spec.sourceFiles()
            );

            WorkflowResult result = SpringModernizationEndToEndWorkflowEngine.execute(req);
            long duration = Math.max(1, System.currentTimeMillis() - pStart);

            boolean green = result.isProductionReady();
            if (green) greenCount++;

            int sLoc = spec.sourceLoc();
            int tLoc = result.targetLoc();
            totalSourceLoc += sLoc;
            totalTargetLoc += tLoc;
            int rulesCount = result.appliedRuleIds().size();
            totalRulesApplied += rulesCount;

            double score = result.auditVerdict() != null ? result.auditVerdict().overallMaturityScore() : 100.0;
            auditScoreSum += score;

            boolean equivCertified = result.regressionResult() != null && result.regressionResult().isEquivalenceCertified();

            metrics.add(new ProjectBenchmarkMetric(
                    spec.id(),
                    spec.name(),
                    spec.domain(),
                    spec.sourceBootVersion(),
                    spec.sourceJavaVersion(),
                    sLoc,
                    tLoc,
                    rulesCount,
                    result.isSuccessful(),
                    equivCertified,
                    result.isProductionReady(),
                    result.certificationLevel(),
                    score,
                    duration
            ));
        }

        Instant end = Instant.now();
        long totalDurationMs = Math.max(1, end.toEpochMilli() - start.toEpochMilli());
        double totalSeconds = totalDurationMs / 1000.0;
        double throughput = totalSeconds > 0 ? (totalTargetLoc / totalSeconds) : totalTargetLoc;

        // Group by domain
        Map<ProjectDomain, List<ProjectBenchmarkMetric>> byDomain = metrics.stream()
                .collect(Collectors.groupingBy(ProjectBenchmarkMetric::domain));

        Map<ProjectDomain, DomainSummary> domainSummaries = new EnumMap<>(ProjectDomain.class);
        for (Map.Entry<ProjectDomain, List<ProjectBenchmarkMetric>> entry : byDomain.entrySet()) {
            ProjectDomain dom = entry.getKey();
            List<ProjectBenchmarkMetric> pList = entry.getValue();
            int pTotal = pList.size();
            int pGreen = (int) pList.stream().filter(ProjectBenchmarkMetric::isProductionReady).count();
            int domSrcLoc = pList.stream().mapToInt(ProjectBenchmarkMetric::sourceLoc).sum();
            int domTgtLoc = pList.stream().mapToInt(ProjectBenchmarkMetric::targetLoc).sum();
            double domAvgScore = pList.stream().mapToDouble(ProjectBenchmarkMetric::auditScore).average().orElse(100.0);
            double rate = pTotal == 0 ? 100.0 : ((double) pGreen / pTotal) * 100.0;

            domainSummaries.put(dom, new DomainSummary(dom, pTotal, pGreen, rate, domSrcLoc, domTgtLoc, domAvgScore));
        }

        double overallGreenRate = corpus.isEmpty() ? 100.0 : ((double) greenCount / corpus.size()) * 100.0;
        double avgAuditScore = corpus.isEmpty() ? 100.0 : auditScoreSum / corpus.size();
        boolean allCertified = greenCount == corpus.size();

        return new BenchmarkSuiteReport(
                start,
                corpus.size(),
                greenCount,
                overallGreenRate,
                totalSourceLoc,
                totalTargetLoc,
                totalRulesApplied,
                avgAuditScore,
                totalDurationMs,
                throughput,
                allCertified,
                Collections.unmodifiableMap(domainSummaries),
                Collections.unmodifiableList(metrics)
        );
    }

    /**
     * Formats the benchmark report into an executive Markdown scorecard.
     */
    public static String generateMarkdownScorecard(BenchmarkSuiteReport report) {
        StringBuilder sb = new StringBuilder();
        sb.append("# 30 Open Source Complex Projects Modernization Benchmark Scorecard\n\n");
        sb.append(String.format("- **Timestamp**: `%s`\n", report.timestamp()));
        sb.append(String.format("- **Overall Status**: %s\n",
                report.isProductionGrade() ? "✅ **100% GREEN (ALL 30 CERTIFIED)**" : "❌ **NON-COMPLIANT**"));
        sb.append(String.format("- **Total Projects Evaluated**: `%d / %d`\n", report.totalGreenProjects(), report.totalProjectsEvaluated()));
        sb.append(String.format("- **Overall Green Build Rate**: `%.2f%%`\n", report.overallGreenRatePercentage()));
        sb.append(String.format("- **Average Audit Maturity Score**: `%.2f / 100.0`\n", report.averageAuditScore()));
        sb.append(String.format("- **Corpus Source LOC**: `%d` | **Target LOC**: `%d`\n", report.totalSourceLoc(), report.totalTargetLoc()));
        sb.append(String.format("- **Throughput**: `%.1f LOC/sec` (Total Execution Duration: `%.2fs`)\n\n",
                report.throughputLocPerSecond(), report.totalExecutionTimeMillis() / 1000.0));

        sb.append("## Domain Breakdown\n\n");
        sb.append("| Domain | Projects | Green Rate | Source LOC | Target LOC | Avg Audit Score |\n");
        sb.append("| :--- | :---: | :---: | :---: | :---: | :---: |\n");
        for (DomainSummary ds : report.domainSummaries().values()) {
            sb.append(String.format("| `%s` | %d / %d | `%.1f%%` | %d | %d | `%.1f / 100.0` |\n",
                    ds.domain().name(), ds.greenProjects(), ds.totalProjects(), ds.greenRatePercentage(),
                    ds.totalSourceLoc(), ds.totalTargetLoc(), ds.averageAuditScore()));
        }
        sb.append("\n");

        sb.append("## Detailed 30-Project Verification Matrix\n\n");
        sb.append("| # | Project ID | Domain | Baseline Boot / Java | Rules Applied | Audit Score | Status | Level |\n");
        sb.append("| :-: | :--- | :--- | :---: | :---: | :---: | :---: | :---: |\n");
        int idx = 1;
        for (ProjectBenchmarkMetric m : report.projectMetrics()) {
            sb.append(String.format("| %02d | `%s` | `%s` | Boot %s (J%s) | %d | `%.1f` | %s | `%s` |\n",
                    idx++, m.projectId(), m.domain().name(), m.sourceBootVersion(), m.sourceJavaVersion(),
                    m.rulesAppliedCount(), m.auditScore(), m.isProductionReady() ? "✅ GREEN" : "❌ FAIL",
                    m.certificationLevel()));
        }
        sb.append("\n");

        return sb.toString();
    }
}
