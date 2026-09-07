package io.elmos.cutover;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.dataformat.yaml.YAMLFactory;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.github.luben.zstd.ZstdOutputStream;

import java.io.BufferedOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

import static io.elmos.cutover.ProductionCutoverModels.*;

/** Writes append-only Batch 11 cutover and migration-acceptance evidence outside both repositories. */
public final class ProductionCutoverArtifactWriter {
    private static final List<String> DIRECTORIES = List.of(
            "cutover/phases", "cutover/gates", "cutover/rollback-points", "cutover/irreversibility-points", "cutover/timeline",
            "waves/wave-plans", "waves/cohorts", "waves/tenant-segments", "waves/region-segments", "waves/results",
            "topology", "schema/expand", "schema/migrate", "schema/contract",
            "data-migration/inventory", "data-migration/mappings", "data-migration/backfill", "data-migration/checkpoints",
            "data-migration/ledger", "data-migration/cdc", "data-migration/reconciliation", "data-migration/conflicts", "data-migration/final-delta",
            "traffic/read-routing", "traffic/write-routing", "traffic/authority-registry", "traffic/fallback", "traffic/sessions", "traffic/long-connections",
            "dual-run/dual-write", "dual-run/dual-read", "dual-run/comparisons", "dual-run/repairs", "dual-run/divergence",
            "integrations/messaging", "integrations/schedulers", "integrations/jobs", "integrations/files", "integrations/search", "integrations/cache",
            "rollback/plans", "rollback/drills", "rollback/reverse-sync", "rollback/compensation", "rollback/forward-fix",
            "hypercare/dashboards", "hypercare/alerts", "hypercare/incidents", "hypercare/daily-reports", "hypercare/exit-report",
            "acceptance/business", "acceptance/engineering", "acceptance/security", "acceptance/operations", "acceptance/compliance",
            "retirement/traffic-drain", "retirement/archives", "retirement/credentials", "retirement/infrastructure",
            "retirement/licenses", "retirement/decommission",
            "handoff/training", "handoff/runbooks", "handoff/ownership", "handoff/operational-readiness",
            "evidence/cutover", "evidence/data", "evidence/rollback", "evidence/acceptance", "evidence/retirement",
            "evidence/migration-acceptance-pack/data-migration", "evidence/migration-acceptance-pack/traffic",
            "evidence/migration-acceptance-pack/messaging", "evidence/migration-acceptance-pack/jobs",
            "evidence/migration-acceptance-pack/files", "evidence/migration-acceptance-pack/hypercare",
            "evidence/migration-acceptance-pack/acceptance", "evidence/migration-acceptance-pack/retirement",
            "evidence/migration-acceptance-pack/risks", "evidence/migration-acceptance-pack/approvals", "reports");
    private static final List<String> REPORTS = List.of(
            "wave-report.json", "backfill-report.json", "cdc-report.json", "dual-write-report.json",
            "dual-read-report.json", "traffic-cutover-report.json", "final-reconciliation-report.json",
            "rollback-readiness-report.json", "hypercare-report.json", "acceptance-report.json",
            "retirement-report.json", "cost-realization-report.json", "final-closure-report.json",
            "batch-11-conformance-report.json");

    private final ObjectMapper json = configured(new ObjectMapper());
    private final ObjectMapper yaml = configured(new ObjectMapper(new YAMLFactory()));

    public Map<String, Path> write(Outcome outcome) throws IOException {
        Objects.requireNonNull(outcome, "outcome");
        Path root = outcome.request().artifactWorkspace().toAbsolutePath().normalize();
        rejectRepositoryRoot(root, outcome.request().sourceRepositoryPath(), "source");
        rejectRepositoryRoot(root, outcome.request().targetRepositoryPath(), "target");
        secureDirectories(root);
        Map<String, Path> written = new LinkedHashMap<>();
        written.put("manifest", atomic(root.resolve("cutover/cutover-run-manifest.yaml"),
                output -> yaml.writeValue(output, runManifest(outcome))));
        written.put("state-machine", atomic(root.resolve("cutover/state-machine.json"),
                output -> json.writeValue(output, stateMachine(outcome))));
        written.put("gate-results", atomic(root.resolve("cutover/gates/gate-results.json"),
                output -> json.writeValue(output, outcome.report())));
        written.put("waves", jsonl(root.resolve("waves/wave-plans/waves.jsonl.zst"), outcome.request().waves()));
        written.put("authorities", jsonl(root.resolve("traffic/authority-registry/write-authorities.jsonl.zst"), outcome.request().authorities()));
        written.put("data-assets", jsonl(root.resolve("data-migration/inventory/data-assets.jsonl.zst"), outcome.request().dataAssets()));
        written.put("approvals", jsonl(root.resolve("evidence/acceptance/approvals.jsonl.zst"), outcome.request().approvals()));
        written.put("topology-schema", evidence(root.resolve("evidence/cutover/topology-schema.json"), outcome.topologySchema()));
        written.put("data-migration", evidence(root.resolve("evidence/data/data-migration.json"), outcome.dataMigration()));
        written.put("traffic", evidence(root.resolve("evidence/cutover/traffic-authority.json"), outcome.traffic()));
        written.put("integrations", evidence(root.resolve("evidence/cutover/integrations.json"), outcome.integrations()));
        written.put("rollback", evidence(root.resolve("evidence/rollback/rollback-incident.json"), outcome.rollback()));
        written.put("hypercare-acceptance", evidence(root.resolve("evidence/acceptance/hypercare-acceptance.json"), outcome.hypercareAcceptance()));
        written.put("retirement", evidence(root.resolve("evidence/retirement/retirement.json"), outcome.retirement()));
        writeAcceptancePack(root, outcome, written);
        for (String report : REPORTS) {
            written.put(report, atomic(root.resolve("reports").resolve(report),
                    output -> json.writeValue(output, reportPayload(report, outcome))));
        }
        return Map.copyOf(written);
    }

    private void writeAcceptancePack(Path root, Outcome outcome, Map<String, Path> written) throws IOException {
        Path pack = root.resolve("evidence/migration-acceptance-pack");
        String summary = "# Migration acceptance summary\n\n"
                + "- Migration: " + outcome.request().migrationId() + "\n"
                + "- Source artifact: " + outcome.request().sourceArtifact().artifactId() + "\n"
                + "- Target artifact: " + outcome.request().targetArtifact().artifactId() + "\n"
                + "- Observed phase: " + outcome.request().currentPhase() + "\n"
                + "- Gate: " + outcome.report().gate() + "\n"
                + "- Migration completed: " + outcome.report().migrationCompleted() + "\n";
        written.put("acceptance-executive-summary", atomic(pack.resolve("executive-summary.md"),
                output -> output.write(summary.getBytes(StandardCharsets.UTF_8))));
        written.put("acceptance-scope", atomic(pack.resolve("source-target-scope.json"), output -> json.writeValue(output,
                Map.of("migration_id", outcome.request().migrationId(), "waves", outcome.request().waves(), "data_assets", outcome.request().dataAssets()))));
        written.put("acceptance-provenance", atomic(pack.resolve("artifact-provenance.json"), output -> json.writeValue(output,
                Map.of("source", outcome.request().sourceArtifact(), "target", outcome.request().targetArtifact()))));
        putJson(written, "pack-backfill", pack.resolve("data-migration/backfill-report.json"), outcome.dataMigration());
        putJson(written, "pack-cdc", pack.resolve("data-migration/cdc-report.json"), outcome.dataMigration());
        putJson(written, "pack-final-position", pack.resolve("data-migration/final-position.json"), outcome.dataMigration());
        putJson(written, "pack-reconciliation", pack.resolve("data-migration/reconciliation-report.json"), outcome.dataMigration());
        putJson(written, "pack-conflicts", pack.resolve("data-migration/conflicts.json"),
                outcome.dataMigration() == null ? Map.of("status", "NOT_RUN") : outcome.dataMigration().assets());
        putJson(written, "pack-read-cutover", pack.resolve("traffic/read-cutover.json"), outcome.traffic());
        putJson(written, "pack-write-cutover", pack.resolve("traffic/write-cutover.json"), outcome.traffic());
        putJson(written, "pack-cohort-routing", pack.resolve("traffic/cohort-routing.json"), outcome.request().waves());
        putJson(written, "pack-fallback", pack.resolve("traffic/fallback-report.json"), outcome.rollback());
        for (ApprovalDimension dimension : List.of(ApprovalDimension.BUSINESS, ApprovalDimension.ENGINEERING,
                ApprovalDimension.SECURITY, ApprovalDimension.OPERATIONS, ApprovalDimension.COMPLIANCE)) {
            putJson(written, "pack-acceptance-" + dimension.name().toLowerCase(Locale.ROOT),
                    pack.resolve("acceptance/" + dimension.name().toLowerCase(Locale.ROOT) + ".json"),
                    acceptance(outcome, dimension));
        }
        putJson(written, "pack-dependency-closure", pack.resolve("retirement/dependency-closure.json"), outcome.retirement());
        putJson(written, "pack-archive", pack.resolve("retirement/archive-report.json"), outcome.retirement());
        putJson(written, "pack-credential-revocation", pack.resolve("retirement/credential-revocation.json"), outcome.retirement());
        putJson(written, "pack-infrastructure", pack.resolve("retirement/infrastructure-destruction.json"), outcome.retirement());
        putJson(written, "pack-license", pack.resolve("retirement/license-termination.json"), outcome.retirement());
        putJson(written, "pack-final-closure", pack.resolve("final-closure-report.json"), outcome.report());
    }

    private Object acceptance(Outcome outcome, ApprovalDimension dimension) {
        List<Approval> approvals = outcome.request().approvals().stream().filter(value -> value.dimension() == dimension).toList();
        return Map.of("dimension", dimension, "approvals", approvals,
                "production_evidence", outcome.hypercareAcceptance() == null ? "NOT_RUN" : outcome.hypercareAcceptance());
    }

    private void putJson(Map<String, Path> written, String key, Path path, Object value) throws IOException {
        written.put(key, atomic(path, output -> json.writeValue(output, value == null ? Map.of("status", "NOT_RUN") : value)));
    }

    private Path evidence(Path path, EvidenceEnvelope evidence) throws IOException {
        return atomic(path, output -> json.writeValue(output, evidence == null ? Map.of("status", "NOT_RUN") : evidence));
    }

    private static Map<String, Object> stateMachine(Outcome outcome) {
        Map<String, Object> model = new LinkedHashMap<>();
        model.put("protocol", "ELMOS-PCCM"); model.put("version", "1.0"); model.put("batch", 11);
        model.put("phases", Phase.values()); model.put("current_phase", outcome.request().currentPhase());
        model.put("gate", outcome.report().gate()); model.put("single_write_authority_required", true);
        model.put("control_plane_executes_production_changes", false);
        return model;
    }

    private static Map<String, Object> runManifest(Outcome outcome) {
        Request request = outcome.request();
        Map<String, Object> manifest = new LinkedHashMap<>();
        manifest.put("batch", 11);
        manifest.put("cutover_run_id", request.cutoverRunId());
        manifest.put("migration_id", request.migrationId());
        manifest.put("source_artifact", request.sourceArtifact());
        manifest.put("target_artifact", request.targetArtifact());
        manifest.put("batch10_eligible", request.batch10Eligible());
        manifest.put("current_phase", request.currentPhase());
        manifest.put("artifact_workspace", request.artifactWorkspace());
        manifest.put("source_repository_path", request.sourceRepositoryPath());
        manifest.put("target_repository_path", request.targetRepositoryPath());
        manifest.put("waves", request.waves());
        manifest.put("authorities", request.authorities());
        manifest.put("data_assets", request.dataAssets());
        manifest.put("approvals", request.approvals());
        manifest.put("policy", request.policy());
        manifest.put("observed_at", request.observedAt());
        manifest.put("production_change_executed", false);
        return manifest;
    }

    private static Object reportPayload(String report, Outcome outcome) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("report", report); payload.put("migration_id", outcome.request().migrationId());
        payload.put("source_artifact_id", outcome.request().sourceArtifact().artifactId());
        payload.put("target_artifact_id", outcome.request().targetArtifact().artifactId());
        payload.put("conformance", outcome.report());
        payload.put("domain_evidence", switch (report) {
            case "wave-report.json" -> Map.of("plans", outcome.request().waves(), "results", outcome.traffic() == null ? List.of() : outcome.traffic().waves());
            case "backfill-report.json", "cdc-report.json", "final-reconciliation-report.json" -> outcome.dataMigration();
            case "dual-write-report.json", "dual-read-report.json", "traffic-cutover-report.json" -> outcome.traffic();
            case "rollback-readiness-report.json" -> outcome.rollback();
            case "hypercare-report.json", "acceptance-report.json" -> outcome.hypercareAcceptance();
            case "retirement-report.json", "cost-realization-report.json" -> outcome.retirement();
            case "final-closure-report.json", "batch-11-conformance-report.json" -> outcome.report();
            default -> Map.of();
        });
        return payload;
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
            throw new FileAlreadyExistsException("Batch 11 evidence is append-only: " + target);
        Path temporary = Files.createTempFile(target.getParent(), ".batch11-", ".tmp");
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
        if (Files.isSymbolicLink(target.getParent())) throw new IOException("symbolic-link parent rejected: " + target.getParent());
    }

    private static void rejectRepositoryRoot(Path root, Path repository, String role) {
        Path normalized = repository.toAbsolutePath().normalize();
        if (root.equals(normalized) || root.startsWith(normalized))
            throw new IllegalArgumentException("artifact workspace cannot be inside the " + role + " repository");
    }

    private static ObjectMapper configured(ObjectMapper mapper) {
        mapper.registerModule(new JavaTimeModule());
        mapper.setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
        mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
        return mapper;
    }

    @FunctionalInterface private interface IoWriter { void write(OutputStream output) throws IOException; }
}
