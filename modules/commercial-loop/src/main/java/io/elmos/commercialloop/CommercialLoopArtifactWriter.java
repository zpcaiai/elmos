package io.elmos.commercialloop;

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

import static io.elmos.commercialloop.CommercialLoopModels.*;

/** Writes atomic, append-only Batch 13 commercial evidence outside the platform repository. */
public final class CommercialLoopArtifactWriter {
    private static final List<String> DIRECTORIES = List.of(
            "commercial-platform/go-to-market/icp", "commercial-platform/go-to-market/accounts",
            "commercial-platform/go-to-market/leads", "commercial-platform/go-to-market/opportunities",
            "commercial-platform/go-to-market/forecasts", "commercial-platform/solution-engineering/discoveries",
            "commercial-platform/solution-engineering/assessments", "commercial-platform/solution-engineering/portfolios",
            "commercial-platform/solution-engineering/pocs", "commercial-platform/solution-engineering/business-cases",
            "commercial-platform/commercial/catalog", "commercial-platform/commercial/pricing",
            "commercial-platform/commercial/cpq", "commercial-platform/commercial/approvals",
            "commercial-platform/commercial/contracts", "commercial-platform/commercial/orders",
            "commercial-platform/commercial/subscriptions", "commercial-platform/onboarding/identity",
            "commercial-platform/onboarding/security", "commercial-platform/onboarding/runners",
            "commercial-platform/onboarding/repositories", "commercial-platform/onboarding/training",
            "commercial-platform/delivery/engagements", "commercial-platform/delivery/projects",
            "commercial-platform/delivery/waves", "commercial-platform/delivery/milestones",
            "commercial-platform/delivery/raid", "commercial-platform/delivery/changes",
            "commercial-platform/delivery/resources", "commercial-platform/delivery/deliverables",
            "commercial-platform/delivery/acceptance", "commercial-platform/support/sla",
            "commercial-platform/support/entitlements", "commercial-platform/support/tickets",
            "commercial-platform/support/incidents", "commercial-platform/support/problems",
            "commercial-platform/support/knowledge", "commercial-platform/customer-success/health",
            "commercial-platform/customer-success/success-plans", "commercial-platform/customer-success/qbr",
            "commercial-platform/customer-success/renewals", "commercial-platform/customer-success/expansion",
            "commercial-platform/customer-success/references", "commercial-platform/partners/program",
            "commercial-platform/partners/onboarding", "commercial-platform/partners/certification",
            "commercial-platform/partners/workspaces", "commercial-platform/partners/deals",
            "commercial-platform/partners/delivery", "commercial-platform/partners/settlements",
            "commercial-platform/partners/marketplace", "commercial-platform/revenue-operations/pipeline",
            "commercial-platform/revenue-operations/forecast", "commercial-platform/revenue-operations/capacity",
            "commercial-platform/revenue-operations/profitability", "commercial-platform/revenue-operations/usage-value",
            "commercial-platform/revenue-operations/product-feedback", "commercial-platform/revenue-operations/commercial-risk",
            "commercial-platform/dashboards/executive", "commercial-platform/dashboards/sales",
            "commercial-platform/dashboards/delivery", "commercial-platform/dashboards/customer-success",
            "commercial-platform/dashboards/partner", "commercial-platform/dashboards/finance",
            "commercial-platform/reports");
    private static final List<String> REPORTS = List.of(
            "icp-performance-report.json", "sales-funnel-report.json", "poc-conversion-report.json",
            "quote-margin-report.json", "onboarding-report.json", "delivery-performance-report.json",
            "sla-support-report.json", "customer-health-report.json", "renewal-report.json",
            "partner-performance-report.json", "profitability-report.json", "value-realization-report.json",
            "batch-13-conformance-report.json");

    private final ObjectMapper json = configured(new ObjectMapper());
    private final ObjectMapper yaml = configured(new ObjectMapper(new YAMLFactory()));

    public Map<String, Path> write(Outcome outcome) throws IOException {
        Objects.requireNonNull(outcome, "outcome");
        Path workspace = outcome.request().artifactWorkspace().toAbsolutePath().normalize();
        rejectRepository(workspace, outcome.request().platformRepositoryPath());
        secureDirectories(workspace);
        Path root = workspace.resolve("commercial-platform");
        Map<String, Path> written = new LinkedHashMap<>();
        written.put("manifest", atomic(root.resolve("revenue-operations/pipeline/commercial-platform-manifest.yaml"),
                output -> yaml.writeValue(output, manifest(outcome))));
        written.put("control-model", atomic(root.resolve("revenue-operations/pipeline/emcom-control-model.json"),
                output -> json.writeValue(output, controlModel(outcome))));
        written.put("gate-results", atomic(root.resolve("revenue-operations/pipeline/batch-13-gate-results.json"),
                output -> json.writeValue(output, outcome.report())));
        written.put("lifecycle", jsonl(root.resolve("go-to-market/opportunities/customer-lifecycle.jsonl.zst"), outcome.request().lifecycleRecords()));
        written.put("domains", jsonl(root.resolve("revenue-operations/pipeline/domain-profiles.jsonl.zst"), outcome.request().domains()));
        written.put("motions", jsonl(root.resolve("commercial/catalog/commercial-motions.jsonl.zst"), outcome.request().motions()));
        written.put("sales-poc-evidence", evidence(root.resolve("solution-engineering/pocs/sales-poc-evidence.json"), outcome.salesPoc()));
        written.put("quote-contract-evidence", evidence(root.resolve("commercial/contracts/quote-contract-evidence.json"), outcome.quoteContract()));
        written.put("onboarding-delivery-evidence", evidence(root.resolve("delivery/acceptance/onboarding-delivery-evidence.json"), outcome.onboardingDelivery()));
        written.put("support-success-evidence", evidence(root.resolve("customer-success/health/support-success-evidence.json"), outcome.supportSuccess()));
        written.put("partner-evidence", evidence(root.resolve("partners/delivery/partner-evidence.json"), outcome.partner()));
        written.put("operations-economics-evidence", evidence(root.resolve("revenue-operations/profitability/operations-economics-evidence.json"), outcome.operationsEconomics()));
        written.put("scale-acceptance-evidence", evidence(root.resolve("dashboards/executive/commercial-scale-acceptance-evidence.json"), outcome.scaleAcceptance()));
        written.put("commercial-evidence-pack", atomic(root.resolve("delivery/deliverables/batch-13-commercial-evidence-pack.json"),
                output -> json.writeValue(output, evidencePack(outcome))));
        for (String report : REPORTS) {
            written.put(report, atomic(root.resolve("reports").resolve(report),
                    output -> json.writeValue(output, reportPayload(report, outcome))));
        }
        return Map.copyOf(written);
    }

    private static Map<String, Object> manifest(Outcome outcome) {
        Request request = outcome.request();
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("batch", 13); value.put("assessment_run_id", request.assessmentRunId());
        value.put("platform_business", request.platformBusiness()); value.put("lifecycle_records", request.lifecycleRecords());
        value.put("domains", request.domains()); value.put("motions", request.motions());
        value.put("policy", request.policy()); value.put("observed_at", request.observedAt());
        value.put("commercial_operation_executed", false);
        return value;
    }

    private static Map<String, Object> controlModel(Outcome outcome) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("protocol", "ELMOS-EMCOM"); value.put("version", "1.0"); value.put("batch", 13);
        value.put("domains", CommercialDomain.values()); value.put("lifecycle_stages", LifecycleStage.values());
        value.put("commercial_motions", CommercialMotion.values()); value.put("gates", Gate.values());
        value.put("highest_gate", outcome.report().gate()); value.put("systems_of_record_are_external", true);
        value.put("control_plane_executes_commercial_operations", false);
        return value;
    }

    private static Map<String, Object> evidencePack(Outcome outcome) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("platform_business_version", outcome.request().platformBusiness().platformBusinessVersion());
        value.put("artifact_digest", outcome.request().platformBusiness().artifactDigest());
        value.put("sales_poc", orNotRun(outcome.salesPoc())); value.put("quote_contract", orNotRun(outcome.quoteContract()));
        value.put("onboarding_delivery", orNotRun(outcome.onboardingDelivery())); value.put("support_success", orNotRun(outcome.supportSuccess()));
        value.put("partner", orNotRun(outcome.partner())); value.put("operations_economics", orNotRun(outcome.operationsEconomics()));
        value.put("scale_acceptance", orNotRun(outcome.scaleAcceptance())); value.put("conformance", outcome.report());
        return value;
    }

    private static Object reportPayload(String report, Outcome outcome) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("report", report); value.put("platform_business_version", outcome.request().platformBusiness().platformBusinessVersion());
        value.put("assessment_run_id", outcome.request().assessmentRunId()); value.put("conformance", outcome.report());
        value.put("domain_evidence", switch (report) {
            case "icp-performance-report.json", "sales-funnel-report.json", "poc-conversion-report.json" -> orNotRun(outcome.salesPoc());
            case "quote-margin-report.json" -> orNotRun(outcome.quoteContract());
            case "onboarding-report.json", "delivery-performance-report.json" -> orNotRun(outcome.onboardingDelivery());
            case "sla-support-report.json", "customer-health-report.json", "renewal-report.json", "value-realization-report.json" -> orNotRun(outcome.supportSuccess());
            case "partner-performance-report.json" -> orNotRun(outcome.partner());
            case "profitability-report.json" -> orNotRun(outcome.operationsEconomics());
            case "batch-13-conformance-report.json" -> outcome.report();
            default -> Map.of();
        });
        return value;
    }

    private static Object orNotRun(Object value) { return value == null ? Map.of("status", "NOT_RUN") : value; }
    private Path evidence(Path target, EvidenceEnvelope value) throws IOException { return atomic(target, output -> json.writeValue(output, orNotRun(value))); }

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
            throw new FileAlreadyExistsException("Batch 13 commercial evidence is append-only: " + target);
        Path temporary = Files.createTempFile(target.getParent(), ".batch13-", ".tmp");
        try {
            try (OutputStream output = Files.newOutputStream(temporary, StandardOpenOption.WRITE)) { writer.write(output); }
            try { Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE); }
            catch (AtomicMoveNotSupportedException ignored) { Files.move(temporary, target); }
            return target;
        } finally { Files.deleteIfExists(temporary); }
    }

    private static void secureDirectories(Path workspace) throws IOException {
        if (Files.exists(workspace, LinkOption.NOFOLLOW_LINKS) && Files.isSymbolicLink(workspace))
            throw new IOException("commercial evidence workspace cannot be a symbolic link");
        if (!Files.exists(workspace, LinkOption.NOFOLLOW_LINKS)) Files.createDirectories(workspace);
        for (String directory : DIRECTORIES) {
            Path current = workspace;
            for (Path part : Path.of(directory)) {
                current = current.resolve(part);
                if (Files.exists(current, LinkOption.NOFOLLOW_LINKS)) {
                    if (Files.isSymbolicLink(current) || !Files.isDirectory(current, LinkOption.NOFOLLOW_LINKS))
                        throw new IOException("unsafe commercial artifact directory: " + current);
                } else Files.createDirectory(current);
            }
        }
    }

    private static void assertSafeTarget(Path target) throws IOException {
        if (Files.isSymbolicLink(target.getParent())) throw new IOException("symbolic-link parent rejected: " + target.getParent());
    }

    private static void rejectRepository(Path workspace, Path repository) throws IOException {
        Path normalized = repository.toAbsolutePath().normalize();
        Path prospectiveWorkspace = prospectiveRealPath(workspace);
        Path realRepository = Files.exists(normalized) ? normalized.toRealPath() : normalized;
        if (workspace.equals(normalized) || workspace.startsWith(normalized)
                || prospectiveWorkspace.equals(realRepository) || prospectiveWorkspace.startsWith(realRepository))
            throw new IllegalArgumentException("commercial evidence workspace cannot be inside the platform repository");
    }

    private static Path prospectiveRealPath(Path path) throws IOException {
        Path existing = path; Deque<Path> missing = new ArrayDeque<>();
        while (!Files.exists(existing)) {
            if (existing.getFileName() != null) missing.push(existing.getFileName());
            existing = existing.getParent();
            if (existing == null) throw new IOException("commercial evidence workspace has no existing ancestor");
        }
        Path resolved = existing.toRealPath();
        while (!missing.isEmpty()) resolved = resolved.resolve(missing.pop());
        return resolved.normalize();
    }

    private static ObjectMapper configured(ObjectMapper mapper) {
        mapper.registerModule(new JavaTimeModule()); mapper.setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
        mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS); return mapper;
    }

    @FunctionalInterface private interface IoWriter { void write(OutputStream output) throws IOException; }
}
