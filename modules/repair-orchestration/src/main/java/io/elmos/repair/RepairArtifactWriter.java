package io.elmos.repair;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.dataformat.yaml.YAMLFactory;
import com.fasterxml.jackson.dataformat.yaml.YAMLGenerator;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.github.luben.zstd.ZstdOutputStream;
import io.elmos.repair.RepairLoopModels.*;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.file.*;
import java.util.*;

/** Writes immutable Batch 8 control-plane evidence outside the target repository. */
public final class RepairArtifactWriter {
    private static final List<String> REQUIRED_DIRECTORIES = List.of(
            "patches/prepared", "patches/applied", "patches/rejected", "patches/rolled-back",
            "patches/conflicts", "patches/human", "agents/compiler", "agents/dependency",
            "agents/static-analysis", "agents/tests", "agents/fixtures", "agents/regression", "agents/review",
            "tests/discovery", "tests/migrated", "tests/fixtures", "tests/failed", "tests/flaky",
            "tests/quarantined", "tests/reports", "snapshots/stable", "snapshots/candidate",
            "snapshots/rolled-back", "evidence/build", "evidence/static-analysis", "evidence/test",
            "evidence/patch", "evidence/agent", "evidence/review", "escalation/build",
            "escalation/semantic", "escalation/test", "escalation/environment", "escalation/security");

    private final ObjectMapper json = new ObjectMapper().registerModule(new JavaTimeModule())
            .enable(SerializationFeature.INDENT_OUTPUT)
            .enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);
    private final ObjectMapper yaml = new ObjectMapper(new YAMLFactory()
            .disable(YAMLGenerator.Feature.WRITE_DOC_START_MARKER)).registerModule(new JavaTimeModule())
            .enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);

    public Map<String,Path> write(Path migrationWorkspace, RunResult result) throws IOException {
        Path root = secureRoot(migrationWorkspace);
        for (String directory : REQUIRED_DIRECTORIES) secureDirectory(root, directory);
        Map<String,Path> written = new LinkedHashMap<>();

        write(root, "repair/repair-run-manifest.yaml", yaml.writeValueAsBytes(result.manifest()), written);
        write(root, "repair/execution-matrix.json", json.writeValueAsBytes(result.matrix()), written);
        write(root, "repair/stop-decision.json", json.writeValueAsBytes(result.stopDecision()), written);
        writeJsonl(root, "repair/commands.jsonl.zst", result.matrix().stream().flatMap(value -> value.commands().stream()).toList(), written);
        writeJsonl(root, "repair/diagnostics.jsonl.zst", result.diagnostics(), written);
        writeJsonl(root, "repair/diagnostic-clusters.jsonl.zst", result.clusters(), written);
        writeJsonl(root, "repair/attribution.jsonl.zst", result.attributions(), written);
        writeJsonl(root, "repair/repair-plans.jsonl.zst", result.plans(), written);
        writeJsonl(root, "repair/progress-history.jsonl.zst", result.progress(), written);

        for (PatchAudit audit : result.patches()) {
            String directory = patchDirectory(audit);
            write(root, directory + "/" + fileName(audit.patch().patchId()) + ".json",
                    json.writeValueAsBytes(audit), written);
        }

        Metrics metrics = result.conformance().metrics();
        Map<String,Object> reports = new LinkedHashMap<>();
        reports.put("reports/build-convergence-report.json", Map.of(
                "dependencyRestoreRate", metrics.dependencyRestoreRate(), "projectLoadRate", metrics.projectLoadRate(),
                "compileRate", metrics.compileRate(), "stopOutcome", result.stopDecision().outcome(),
                "modules", result.finalExecution().moduleExecutions()));
        reports.put("reports/static-analysis-report.json", Map.of(
                "diagnostics", result.diagnostics().size(), "classificationRate", metrics.diagnosticClassificationRate(),
                "blocking", result.finalExecution().blockingStaticDiagnostics(),
                "critical", result.finalExecution().criticalStaticDiagnostics()));
        reports.put("reports/test-migration-report.json", Map.of(
                "discoveryRate", metrics.testDiscoveryRate(), "requiredExecutionRate", metrics.requiredTestExecutionRate(),
                "tests", result.finalExecution().tests(), "modules", result.finalExecution().moduleExecutions()));
        reports.put("reports/test-regression-report.json", Map.of(
                "unitPassRate", metrics.unitPassRate(), "contractPassRate", metrics.contractPassRate(),
                "integrationPassRate", metrics.integrationPassRate(),
                "fullRegressionExecuted", result.finalExecution().fullRegressionExecuted()));
        reports.put("reports/flaky-test-report.json", Map.of(
                "flakyRate", metrics.flakyRate(), "tests", result.finalExecution().tests().stream()
                        .filter(value -> value.status() == TestStatus.FLAKY).toList()));
        reports.put("reports/patch-effectiveness-report.json", result.patches());
        reports.put("reports/agent-performance-report.json", Map.of(
                "agentCalls", result.stopDecision().agentCalls(), "agentTokens", result.stopDecision().agentTokens(),
                "verifiedAgentPatches", result.patches().stream().filter(value -> value.patch().agentGenerated()
                        && Set.of(PatchOutcome.EFFECTIVE, PatchOutcome.PARTIALLY_EFFECTIVE).contains(value.outcome())).count()));
        reports.put("reports/repair-cost-report.json", Map.of(
                "agentTokens", result.stopDecision().agentTokens(), "costMicros", result.stopDecision().costMicros(),
                "rounds", result.stopDecision().rounds(), "patchAttempts", result.stopDecision().patchAttempts()));
        reports.put("reports/unresolved-cluster-report.json", Map.of(
                "blockers", result.conformance().blockingErrors(), "openObligations", result.conformance().openObligations(),
                "clusters", result.clusters()));
        reports.put("reports/reproducibility-report.json", Map.of(
                "runsPassed", metrics.reproducibilityRunsPassed(), "environmentHash", result.manifest().environmentHash(),
                "required", metrics.reproducibilityRunsPassed() >= 2));
        reports.put("reports/batch-8-conformance-report.json", result.conformance());
        reports.put("evidence/index.json", Map.of(
                "repairRunId", result.manifest().repairRunId(), "evidenceRefs", result.finalExecution().evidenceRefs(),
                "patchIds", result.manifest().patchIds(), "stableSnapshot", result.stopDecision().stableSnapshotId()));
        for (Map.Entry<String,Object> report : reports.entrySet())
            write(root, report.getKey(), json.writeValueAsBytes(report.getValue()), written);
        return Map.copyOf(written);
    }

    private void writeJsonl(Path root, String relative, List<?> values, Map<String,Path> written) throws IOException {
        ByteArrayOutputStream compressed = new ByteArrayOutputStream();
        try (ZstdOutputStream output = new ZstdOutputStream(compressed)) {
            for (Object value : values) {
                output.write(json.writeValueAsBytes(value));
                output.write('\n');
            }
        }
        write(root, relative, compressed.toByteArray(), written);
    }

    private void write(Path root, String relative, byte[] bytes, Map<String,Path> written) throws IOException {
        Path target = secureTarget(root, relative);
        atomicWrite(target, bytes);
        written.put(relative, target);
    }

    private String patchDirectory(PatchAudit audit) {
        if (audit.application().state() == PatchState.REJECTED) return "patches/rejected";
        if (audit.application().state() == PatchState.CONFLICTED) return "patches/conflicts";
        if ("ROLLED_BACK".equals(audit.rollbackStatus())) return "patches/rolled-back";
        if (audit.patch().humanReviewApproved()) return "patches/human";
        return "patches/applied";
    }

    private static String fileName(String value) { return value.replaceAll("[^A-Za-z0-9._-]", "-"); }

    private Path secureRoot(Path requested) throws IOException {
        Path root = requested.toAbsolutePath().normalize();
        if (Files.exists(root, LinkOption.NOFOLLOW_LINKS) && Files.isSymbolicLink(root))
            throw new SecurityException("REPAIR_WORKSPACE_SYMLINK");
        Files.createDirectories(root);
        if (Files.isSymbolicLink(root)) throw new SecurityException("REPAIR_WORKSPACE_SYMLINK");
        return root.toRealPath(LinkOption.NOFOLLOW_LINKS);
    }

    private Path secureDirectory(Path root, String relative) throws IOException {
        Path sentinel = secureTarget(root, relative + "/.directory-sentinel");
        Path directory = sentinel.getParent();
        if (!directory.toRealPath(LinkOption.NOFOLLOW_LINKS).startsWith(root))
            throw new SecurityException("REPAIR_DIRECTORY_ESCAPE:" + relative);
        return directory;
    }

    private Path secureTarget(Path root, String relative) throws IOException {
        Path target = root.resolve(relative).normalize();
        if (!target.startsWith(root)) throw new SecurityException("REPAIR_ARTIFACT_PATH_ESCAPE");
        Path current = root;
        for (Path part : root.relativize(target.getParent())) {
            current = current.resolve(part);
            if (Files.exists(current, LinkOption.NOFOLLOW_LINKS) && Files.isSymbolicLink(current))
                throw new SecurityException("REPAIR_ARTIFACT_PARENT_SYMLINK:" + current);
            if (!Files.exists(current, LinkOption.NOFOLLOW_LINKS)) Files.createDirectory(current);
            if (!current.toRealPath(LinkOption.NOFOLLOW_LINKS).startsWith(root))
                throw new SecurityException("REPAIR_ARTIFACT_PARENT_ESCAPE:" + current);
        }
        if (Files.exists(target, LinkOption.NOFOLLOW_LINKS) && Files.isSymbolicLink(target))
            throw new SecurityException("REPAIR_ARTIFACT_SYMLINK:" + target);
        return target;
    }

    private void atomicWrite(Path target, byte[] bytes) throws IOException {
        Path temporary = Files.createTempFile(target.getParent(), target.getFileName().toString(), ".tmp");
        try {
            Files.write(temporary, bytes, StandardOpenOption.TRUNCATE_EXISTING);
            try {
                Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException ignored) {
                Files.move(temporary, target, StandardCopyOption.REPLACE_EXISTING);
            }
        } finally {
            Files.deleteIfExists(temporary);
        }
    }
}
