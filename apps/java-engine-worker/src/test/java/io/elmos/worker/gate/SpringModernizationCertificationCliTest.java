package io.elmos.worker.gate;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class SpringModernizationCertificationCliTest {

    @Test
    @DisplayName("Execute Certification CLI in memory and verify zero exit code with full output")
    void testCliExecutionInMemory() {
        ByteArrayOutputStream outBuf = new ByteArrayOutputStream();
        ByteArrayOutputStream errBuf = new ByteArrayOutputStream();
        PrintStream out = new PrintStream(outBuf, true, StandardCharsets.UTF_8);
        PrintStream err = new PrintStream(errBuf, true, StandardCharsets.UTF_8);

        var result = SpringModernizationCertificationCli.run(new String[0], out, err);

        assertNotNull(result);
        assertEquals(0, result.exitCode(), "Exit code must be 0 for certified production readiness");
        assertTrue(result.isSuccess());
        assertNotNull(result.benchmarkReport());
        assertNotNull(result.gateVerdict());
        assertTrue(result.gateVerdict().isCertifiedForProduction());

        String stdout = outBuf.toString(StandardCharsets.UTF_8);
        assertTrue(stdout.contains("ELMOS SPRING ENTERPRISE MODERNIZATION PRODUCTION CERTIFICATION GATE"));
        assertTrue(stdout.contains("100% GREEN (ALL 30 CERTIFIED)"));
        assertTrue(stdout.contains("Official Industrial Production Certification Certificate"));
    }

    @Test
    @DisplayName("Execute Certification CLI with --output-dir and verify file persistence")
    void testCliExecutionWithOutputDir(@TempDir Path tempDir) {
        ByteArrayOutputStream outBuf = new ByteArrayOutputStream();
        ByteArrayOutputStream errBuf = new ByteArrayOutputStream();
        PrintStream out = new PrintStream(outBuf, true, StandardCharsets.UTF_8);
        PrintStream err = new PrintStream(errBuf, true, StandardCharsets.UTF_8);

        String[] args = new String[]{"--output-dir", tempDir.toAbsolutePath().toString()};
        var result = SpringModernizationCertificationCli.run(args, out, err);

        assertEquals(0, result.exitCode());
        Path scoreFile = tempDir.resolve("MODERNIZATION_SCORECARD.md");
        Path certFile = tempDir.resolve("CERTIFICATION_GATE_VERDICT.md");

        assertTrue(Files.exists(scoreFile), "Scorecard file must be persisted");
        assertTrue(Files.exists(certFile), "Verdict certificate file must be persisted");
    }
}
