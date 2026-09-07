package io.elmos.hardening;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.dataformat.yaml.YAMLFactory;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.github.luben.zstd.ZstdOutputStream;

import java.io.BufferedOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.*;
import java.util.*;

import static io.elmos.hardening.ProductionHardeningModels.*;

/** Writes the append-only Batch 10 evidence tree outside the migrated repository. */
public final class ProductionHardeningArtifactWriter {
    private static final List<String> DIRECTORIES = List.of(
            "production-hardening",
            "performance/workload-models", "performance/scenarios", "performance/executions",
            "performance/latency", "performance/throughput", "performance/resources", "performance/profiles",
            "performance/saturation", "performance/soak", "performance/capacity", "performance/regression",
            "security/threat-models", "security/sbom", "security/vulnerability", "security/sast", "security/dast",
            "security/secrets", "security/authentication", "security/authorization", "security/tenant-isolation",
            "security/data-protection", "security/container", "security/iac",
            "reliability/fault-models", "reliability/chaos-experiments", "reliability/dependency-failures",
            "reliability/timeout-retry", "reliability/circuit-breaker", "reliability/bulkhead",
            "reliability/backpressure", "reliability/graceful-degradation", "reliability/crash-consistency",
            "reliability/backup-restore", "reliability/disaster-recovery",
            "observability/telemetry-contract", "observability/logs", "observability/metrics",
            "observability/traces", "observability/correlation", "observability/dashboards",
            "observability/alerts", "observability/runbooks",
            "slo/sli-definitions", "slo/slo-definitions", "slo/error-budgets", "slo/burn-rates", "slo/reports",
            "release/artifacts", "release/provenance", "release/signatures", "release/canary",
            "release/blue-green", "release/rollback", "release/forward-fix", "release/approvals",
            "costs/capacity-cost", "costs/unit-cost", "costs/source-target-comparison", "costs/forecasts",
            "evidence/performance", "evidence/security", "evidence/chaos", "evidence/recovery",
            "evidence/observability", "evidence/release", "evidence/production-readiness-pack", "reports");
    private static final List<String> REPORTS = List.of(
            "performance-report.json", "capacity-report.json", "soak-report.json", "threat-model-report.json",
            "vulnerability-report.json", "application-security-report.json", "tenant-isolation-report.json",
            "chaos-report.json", "recovery-report.json", "backup-restore-report.json",
            "disaster-recovery-report.json", "observability-report.json", "slo-report.json",
            "canary-report.json", "rollback-report.json", "cost-report.json",
            "production-readiness-report.json", "batch-10-conformance-report.json");

    private final ObjectMapper json = configured(new ObjectMapper());
    private final ObjectMapper yaml = configured(new ObjectMapper(new YAMLFactory()));

    public Map<String, Path> write(Outcome outcome) throws IOException {
        Objects.requireNonNull(outcome, "outcome");
        Path root = outcome.request().artifactWorkspace().toAbsolutePath().normalize();
        rejectRepositoryRoot(root, outcome.request().targetRepositoryPath());
        secureDirectories(root);
        Map<String, Path> written = new LinkedHashMap<>();
        written.put("manifest", atomic(root.resolve("production-hardening/hardening-run-manifest.yaml"),
                output -> yaml.writeValue(output, outcome.request())));
        written.put("risk-profiles", jsonl(root.resolve("production-hardening/risk-profiles.jsonl.zst"),
                outcome.request().riskProfiles()));
        written.put("production-readiness-model", atomic(root.resolve("production-hardening/production-readiness-model.json"),
                output -> json.writeValue(output, readinessModel(outcome))));
        written.put("gate-results", atomic(root.resolve("production-hardening/gate-results.json"),
                output -> json.writeValue(output, outcome.report())));
        written.put("workload-models", jsonl(root.resolve("performance/workload-models/workload-models.jsonl.zst"),
                outcome.request().workloadModels()));
        written.put("scenarios", jsonl(root.resolve("performance/scenarios/scenarios.jsonl.zst"),
                outcome.request().scenarios()));
        written.put("calibrations", jsonl(root.resolve("performance/executions/calibrations.jsonl.zst"),
                outcome.calibrations().values()));
        written.put("performance-evidence", jsonl(root.resolve("evidence/performance/evidence.jsonl.zst"), outcome.performance().values()));
        written.put("security-evidence", jsonl(root.resolve("evidence/security/evidence.jsonl.zst"), outcome.security().values()));
        written.put("reliability-evidence", jsonl(root.resolve("evidence/recovery/evidence.jsonl.zst"), outcome.reliability().values()));
        written.put("observability-evidence", jsonl(root.resolve("evidence/observability/evidence.jsonl.zst"), outcome.observability().values()));
        written.put("release-evidence", jsonl(root.resolve("evidence/release/evidence.jsonl.zst"), outcome.release().values()));
        written.put("cost-evidence", jsonl(root.resolve("costs/unit-cost/evidence.jsonl.zst"), outcome.costs().values()));
        written.put("readiness-evidence-pack", atomic(
                root.resolve("evidence/production-readiness-pack/production-readiness-evidence-pack.json"),
                output -> json.writeValue(output, evidencePack(outcome))));
        for (String report : REPORTS) {
            Path target = root.resolve("reports").resolve(report);
            written.put(report, atomic(target, output -> json.writeValue(output, reportPayload(report, outcome))));
        }
        return Map.copyOf(written);
    }

    private static Map<String, Object> readinessModel(Outcome outcome) {
        Map<String, Object> model = new LinkedHashMap<>();
        model.put("protocol", "ELMOS-PRM"); model.put("version", "1.0"); model.put("batch", 10);
        model.put("artifact_id", outcome.request().targetArtifactId());
        model.put("dimensions", List.of("performance", "security", "reliability", "observability",
                "operability", "release-safety"));
        model.put("maximum_claim", "eligible-for-progressive-delivery");
        model.put("production_ready", false); model.put("eligible_for_cutover", false);
        return model;
    }

    private static Object reportPayload(String report, Outcome outcome) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("report", report); payload.put("hardening_run_id", outcome.request().hardeningRunId());
        payload.put("artifact_id", outcome.request().targetArtifactId()); payload.put("conformance", outcome.report());
        Object domainEvidence = switch (report) {
            case "performance-report.json", "capacity-report.json", "soak-report.json" -> Map.of(
                    "calibrations", outcome.calibrations(), "performance", outcome.performance(), "costs", outcome.costs());
            case "threat-model-report.json", "vulnerability-report.json", "application-security-report.json",
                    "tenant-isolation-report.json" -> outcome.security();
            case "chaos-report.json", "recovery-report.json", "backup-restore-report.json",
                    "disaster-recovery-report.json" -> outcome.reliability();
            case "observability-report.json", "slo-report.json" -> outcome.observability();
            case "canary-report.json", "rollback-report.json" -> outcome.release();
            case "cost-report.json" -> outcome.costs();
            case "production-readiness-report.json" -> evidencePack(outcome);
            default -> Map.of();
        };
        payload.put("domain_evidence", domainEvidence);
        payload.put("production_ready", false); payload.put("eligible_for_cutover", false);
        return payload;
    }

    private static Map<String, Object> evidencePack(Outcome outcome) {
        Map<String, Object> pack = new LinkedHashMap<>();
        pack.put("protocol", "ELMOS-PRM"); pack.put("version", "1.0"); pack.put("batch", 10);
        pack.put("artifact_id", outcome.request().targetArtifactId());
        pack.put("dimensions", List.of("performance", "security", "reliability", "observability",
                "operability", "release-safety"));
        pack.put("service_gates", outcome.report().services());
        pack.put("evidence_refs", outcome.report().services().stream().flatMap(gate -> gate.evidenceRefs().stream())
                .distinct().toList());
        pack.put("eligible_for_progressive_delivery", outcome.report().eligibleForProgressiveDelivery());
        pack.put("append_only", true);
        pack.put("redacted", true); pack.put("calibrations", outcome.calibrations());
        pack.put("performance", outcome.performance()); pack.put("security", outcome.security());
        pack.put("reliability", outcome.reliability()); pack.put("observability", outcome.observability());
        pack.put("release", outcome.release()); pack.put("costs", outcome.costs()); pack.put("conformance", outcome.report());
        pack.put("production_ready", false); pack.put("eligible_for_cutover", false);
        return pack;
    }

    private Path jsonl(Path target, Collection<?> values) throws IOException {
        return atomic(target, raw -> {
            try (ZstdOutputStream zstd = new ZstdOutputStream(new BufferedOutputStream(raw))) {
                for (Object value : values) { zstd.write(json.writeValueAsBytes(value)); zstd.write('\n'); }
            }
        });
    }

    private Path atomic(Path target, IoWriter writer) throws IOException {
        assertSafeTarget(target);
        if (Files.exists(target, LinkOption.NOFOLLOW_LINKS))
            throw new FileAlreadyExistsException("Batch 10 evidence is append-only: " + target);
        Path temporary = Files.createTempFile(target.getParent(), ".batch10-", ".tmp");
        try {
            try (OutputStream output = Files.newOutputStream(temporary, StandardOpenOption.WRITE)) { writer.write(output); }
            try { Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE); }
            catch (AtomicMoveNotSupportedException ignored) { Files.move(temporary, target); }
            return target;
        } finally { Files.deleteIfExists(temporary); }
    }

    private static void secureDirectories(Path root) throws IOException {
        if (Files.exists(root, LinkOption.NOFOLLOW_LINKS) && Files.isSymbolicLink(root))
            throw new IOException("artifact workspace cannot be a symbolic link");
        if (!Files.exists(root, LinkOption.NOFOLLOW_LINKS)) Files.createDirectories(root);
        for (String directory : DIRECTORIES) {
            Path current = root;
            for (Path part : Path.of(directory)) {
                current = current.resolve(part);
                if (Files.exists(current, LinkOption.NOFOLLOW_LINKS)) {
                    if (Files.isSymbolicLink(current) || !Files.isDirectory(current, LinkOption.NOFOLLOW_LINKS))
                        throw new IOException("unsafe artifact directory: " + current);
                } else Files.createDirectory(current);
            }
        }
    }

    private static void assertSafeTarget(Path target) throws IOException {
        Path parent = target.getParent();
        if (Files.isSymbolicLink(parent)) throw new IOException("symbolic-link parent rejected: " + parent);
    }

    private static void rejectRepositoryRoot(Path root, Path repository) {
        Path normalized = repository.toAbsolutePath().normalize();
        if (root.equals(normalized) || root.startsWith(normalized))
            throw new IllegalArgumentException("artifact workspace cannot be inside the target repository");
    }

    private static ObjectMapper configured(ObjectMapper mapper) {
        mapper.registerModule(new JavaTimeModule());
        mapper.setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
        mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
        return mapper;
    }

    @FunctionalInterface private interface IoWriter { void write(OutputStream output) throws IOException; }
}
