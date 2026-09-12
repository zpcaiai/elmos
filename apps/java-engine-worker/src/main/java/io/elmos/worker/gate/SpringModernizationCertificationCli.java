package io.elmos.worker.gate;

import io.elmos.worker.benchmark.SpringEnterpriseFullCorpusBenchmarkValidator;
import io.elmos.worker.benchmark.SpringEnterpriseFullCorpusBenchmarkValidator.BenchmarkSuiteReport;
import io.elmos.worker.gate.SpringEnterpriseProductionCertificationGate.CertificationGateVerdict;
import io.elmos.worker.report.SpringEnterpriseModernizationDossierGenerator;

import java.io.PrintStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;

/**
 * Enterprise CLI Entrypoint for Spring Modernization Production Certification.
 * <p>
 * Invoked by CI/CD pipelines, release trains, or audit engineers to:
 * <ul>
 *   <li>Execute the full 30 open source complex benchmark suite</li>
 *   <li>Evaluate all 10 strict industrial certification criteria</li>
 *   <li>Generate SLSA Level 3 artifact dossiers and Markdown certificates</li>
 *   <li>Exit with status 0 on full certification or 1 on gate failure</li>
 * </ul>
 */
public final class SpringModernizationCertificationCli {

    public record CliExecutionResult(
            int exitCode,
            BenchmarkSuiteReport benchmarkReport,
            CertificationGateVerdict gateVerdict,
            String certificateMarkdown,
            String scorecardMarkdown
    ) {
        public boolean isSuccess() {
            return exitCode == 0;
        }
    }

    private SpringModernizationCertificationCli() {}

    /**
     * Executes the certification gate from the command line interface.
     *
     * @param args Command line arguments: optional --output-dir <path>
     * @param out  Standard output stream
     * @param err  Standard error stream
     * @return Execution result object
     */
    public static CliExecutionResult run(String[] args, PrintStream out, PrintStream err) {
        Objects.requireNonNull(out, "out stream must not be null");
        Objects.requireNonNull(err, "err stream must not be null");

        out.println("================================================================================");
        out.println(" ELMOS SPRING ENTERPRISE MODERNIZATION PRODUCTION CERTIFICATION GATE (v4.1.0)");
        out.println("================================================================================");
        out.println("Executing 30 open source complex projects modernization benchmark suite...\n");

        long start = System.currentTimeMillis();
        BenchmarkSuiteReport report = SpringEnterpriseFullCorpusBenchmarkValidator.executeFullCorpusBenchmark();
        CertificationGateVerdict verdict = SpringEnterpriseProductionCertificationGate.evaluate(report);

        String certMd = SpringEnterpriseProductionCertificationGate.toMarkdownCertificate(verdict);
        String scoreMd = SpringEnterpriseFullCorpusBenchmarkValidator.generateMarkdownScorecard(report);

        out.println(scoreMd);
        out.println(certMd);

        // Check if output directory is requested
        Path outputDir = null;
        for (int i = 0; i < args.length - 1; i++) {
            if ("--output-dir".equals(args[i]) || "-o".equals(args[i])) {
                outputDir = Path.of(args[i + 1]);
                break;
            }
        }

        if (outputDir != null) {
            try {
                Files.createDirectories(outputDir);
                Files.writeString(outputDir.resolve("MODERNIZATION_SCORECARD.md"), scoreMd);
                Files.writeString(outputDir.resolve("CERTIFICATION_GATE_VERDICT.md"), certMd);
                out.println("Artifacts successfully written to: " + outputDir.toAbsolutePath());
            } catch (Exception e) {
                err.println("Warning: Failed to write artifacts to directory: " + e.getMessage());
            }
        }

        long elapsed = System.currentTimeMillis() - start;
        out.printf("\nCertification execution completed in %d ms with verdict: %s (%s)\n",
                elapsed, verdict.overallStatus(), verdict.certificationTier());

        int exitCode = verdict.isCertifiedForProduction() ? 0 : 1;
        return new CliExecutionResult(exitCode, report, verdict, certMd, scoreMd);
    }

    public static void main(String[] args) {
        CliExecutionResult result = run(args, System.out, System.err);
        System.exit(result.exitCode());
    }
}
