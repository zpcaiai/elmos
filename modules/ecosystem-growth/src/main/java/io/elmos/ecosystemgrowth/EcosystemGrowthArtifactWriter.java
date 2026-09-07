package io.elmos.ecosystemgrowth;

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

import static io.elmos.ecosystemgrowth.EcosystemGrowthModels.*;

/** Writes atomic, append-only Batch 14 growth evidence outside the platform repository. */
public final class EcosystemGrowthArtifactWriter {
    private static final List<String> DIRECTORIES = List.of(
            "growth-platform/growth-core/north-star", "growth-platform/growth-core/journeys",
            "growth-platform/growth-core/funnels", "growth-platform/growth-core/events",
            "growth-platform/growth-core/experiments", "growth-platform/growth-core/attribution",
            "growth-platform/product-growth/signup", "growth-platform/product-growth/activation",
            "growth-platform/product-growth/onboarding", "growth-platform/product-growth/trial",
            "growth-platform/product-growth/lifecycle", "growth-platform/product-growth/referral",
            "growth-platform/product-growth/expansion",
            "growth-platform/content/strategy", "growth-platform/content/topic-clusters",
            "growth-platform/content/production", "growth-platform/content/seo",
            "growth-platform/content/comparisons", "growth-platform/content/case-studies",
            "growth-platform/content/events", "growth-platform/content/research",
            "growth-platform/developer-ecosystem/portal", "growth-platform/developer-ecosystem/docs",
            "growth-platform/developer-ecosystem/api", "growth-platform/developer-ecosystem/cli",
            "growth-platform/developer-ecosystem/sdk", "growth-platform/developer-ecosystem/starters",
            "growth-platform/developer-ecosystem/samples", "growth-platform/developer-ecosystem/sandbox",
            "growth-platform/developer-ecosystem/devrel",
            "growth-platform/community/spaces", "growth-platform/community/content",
            "growth-platform/community/reputation", "growth-platform/community/moderation",
            "growth-platform/community/ambassadors", "growth-platform/community/events",
            "growth-platform/community/knowledge-loop",
            "growth-platform/marketplace/publishers", "growth-platform/marketplace/assets",
            "growth-platform/marketplace/certification", "growth-platform/marketplace/discovery",
            "growth-platform/marketplace/installation", "growth-platform/marketplace/pricing",
            "growth-platform/marketplace/reviews", "growth-platform/marketplace/payouts",
            "growth-platform/marketplace/bounties", "growth-platform/marketplace/trust-safety",
            "growth-platform/internationalization/i18n", "growth-platform/internationalization/localization",
            "growth-platform/internationalization/terminology",
            "growth-platform/internationalization/translation-memory",
            "growth-platform/internationalization/locale-formats",
            "growth-platform/internationalization/linguistic-qa",
            "growth-platform/regional-growth/assessments",
            "growth-platform/regional-growth/launch-playbooks",
            "growth-platform/regional-growth/design-partners",
            "growth-platform/regional-growth/content", "growth-platform/regional-growth/communities",
            "growth-platform/regional-growth/channels",
            "growth-platform/regional-growth/cloud-marketplaces",
            "growth-platform/regional-growth/support", "growth-platform/regional-growth/metrics",
            "growth-platform/economics/cac", "growth-platform/economics/ltv",
            "growth-platform/economics/channel", "growth-platform/economics/marketplace",
            "growth-platform/economics/regional", "growth-platform/economics/contribution-margin",
            "growth-platform/governance/brand", "growth-platform/governance/claims",
            "growth-platform/governance/privacy", "growth-platform/governance/safety",
            "growth-platform/governance/risk", "growth-platform/governance/playbooks",
            "growth-platform/reports");

    private static final List<String> REPORTS = List.of(
            "product-growth-report.json", "activation-retention-report.json",
            "channel-attribution-report.json", "content-performance-report.json",
            "developer-ecosystem-report.json", "community-health-report.json",
            "marketplace-growth-report.json", "localization-quality-report.json",
            "regional-launch-report.json", "channel-economics-report.json",
            "growth-risk-report.json", "batch-14-conformance-report.json");

    private final ObjectMapper json = configured(new ObjectMapper());
    private final ObjectMapper yaml = configured(new ObjectMapper(new YAMLFactory()));

    public Map<String, Path> write(Outcome outcome) throws IOException {
        Objects.requireNonNull(outcome, "outcome");
        Path workspace = outcome.request().artifactWorkspace().toAbsolutePath().normalize();
        rejectRepository(workspace, outcome.request().platformRepositoryPath());
        secureDirectories(workspace);
        Path root = workspace.resolve("growth-platform");
        Map<String, Path> written = new LinkedHashMap<>();
        written.put("manifest", atomic(root.resolve("growth-core/north-star/growth-program-manifest.yaml"),
                output -> yaml.writeValue(output, manifest(outcome))));
        written.put("control-model", atomic(root.resolve("growth-core/north-star/pegm-control-model.json"),
                output -> json.writeValue(output, controlModel(outcome))));
        written.put("gate-results", atomic(root.resolve("governance/risk/batch-14-gate-results.json"),
                output -> json.writeValue(output, outcome.report())));
        written.put("growth-domains", jsonl(root.resolve(
                "growth-core/journeys/growth-domain-profiles.jsonl.zst"),
                outcome.request().growthDomains()));
        written.put("flywheels", jsonl(root.resolve(
                "growth-core/funnels/growth-flywheel-profiles.jsonl.zst"),
                outcome.request().flywheels()));
        for (AssuranceArea area : AssuranceArea.values()) {
            String key = area.name().toLowerCase(Locale.ROOT).replace('_', '-');
            written.put(key + "-evidence", evidence(root.resolve(areaEvidencePath(area)),
                    outcome.gateEvidence().get(area)));
        }
        written.put("growth-conformance-evidence", evidence(
                root.resolve("governance/risk/growth-conformance-evidence.json"),
                outcome.acceptance()));
        written.put("growth-evidence-pack", atomic(
                root.resolve("governance/playbooks/batch-14-growth-evidence-pack.json"),
                output -> json.writeValue(output, evidencePack(outcome))));
        for (String report : REPORTS) {
            written.put(report, atomic(root.resolve("reports").resolve(report),
                    output -> json.writeValue(output, reportPayload(report, outcome))));
        }
        return Map.copyOf(written);
    }

    private static String areaEvidencePath(AssuranceArea area) {
        return switch (area) {
            case PRODUCT_ACTIVATION -> "product-growth/activation/g14-a-product-activation-evidence.json";
            case CONTENT_AND_DEVELOPER -> "developer-ecosystem/docs/g14-b-content-developer-evidence.json";
            case COMMUNITY_SAFETY -> "community/moderation/g14-c-community-evidence.json";
            case MARKETPLACE_GROWTH -> "marketplace/certification/g14-d-marketplace-evidence.json";
            case INTERNATIONALIZATION ->
                    "internationalization/linguistic-qa/g14-e-internationalization-evidence.json";
            case REGIONAL_CHANNEL -> "regional-growth/metrics/g14-f-regional-channel-evidence.json";
        };
    }

    private static Map<String, Object> manifest(Outcome outcome) {
        Request request = outcome.request();
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("batch", 14);
        value.put("assessment_run_id", request.assessmentRunId());
        value.put("platform_business", request.platformBusiness());
        value.put("growth_program", request.growthProgram());
        value.put("north_star", request.northStar());
        value.put("growth_domains", request.growthDomains());
        value.put("flywheels", request.flywheels());
        value.put("policy", request.policy());
        value.put("observed_at", request.observedAt());
        value.put("external_operation_executed", false);
        return value;
    }

    private static Map<String, Object> controlModel(Outcome outcome) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("protocol", "ELMOS-PEGM");
        value.put("version", "growth-ecosystem-v1");
        value.put("batch", 14);
        value.put("growth_domains", GrowthDomain.values());
        value.put("flywheels", Flywheel.values());
        value.put("assurance_areas", AssuranceArea.values());
        value.put("gates", Gate.values());
        value.put("highest_gate", outcome.report().gate());
        value.put("required_controls", Arrays.stream(AssuranceArea.values()).collect(
                java.util.stream.Collectors.toMap(Enum::name, EcosystemGrowthService::requiredFor)));
        value.put("systems_of_record_are_external", true);
        value.put("control_plane_executes_external_operations", false);
        return value;
    }

    private static Map<String, Object> evidencePack(Outcome outcome) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("growth_platform_version", "growth-ecosystem-v1");
        value.put("platform_business_version",
                outcome.request().platformBusiness().platformBusinessVersion());
        value.put("artifact_digest", outcome.request().platformBusiness().artifactDigest());
        value.put("gate_evidence", Arrays.stream(AssuranceArea.values())
                .map(area -> orNotRun(outcome.gateEvidence().get(area))).toList());
        value.put("growth_conformance", orNotRun(outcome.acceptance()));
        value.put("conformance", outcome.report());
        value.put("external_operation_executed", false);
        return value;
    }

    private static Map<String, Object> reportPayload(String report, Outcome outcome) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("report", report);
        value.put("growth_platform_version", "growth-ecosystem-v1");
        value.put("platform_business_version",
                outcome.request().platformBusiness().platformBusinessVersion());
        value.put("assessment_run_id", outcome.request().assessmentRunId());
        value.put("conformance", outcome.report());
        value.put("gate_evidence", switch (report) {
            case "product-growth-report.json", "activation-retention-report.json" ->
                    orNotRun(outcome.gateEvidence().get(AssuranceArea.PRODUCT_ACTIVATION));
            case "channel-attribution-report.json", "content-performance-report.json",
                    "developer-ecosystem-report.json" ->
                    orNotRun(outcome.gateEvidence().get(AssuranceArea.CONTENT_AND_DEVELOPER));
            case "community-health-report.json" ->
                    orNotRun(outcome.gateEvidence().get(AssuranceArea.COMMUNITY_SAFETY));
            case "marketplace-growth-report.json" ->
                    orNotRun(outcome.gateEvidence().get(AssuranceArea.MARKETPLACE_GROWTH));
            case "localization-quality-report.json" ->
                    orNotRun(outcome.gateEvidence().get(AssuranceArea.INTERNATIONALIZATION));
            case "regional-launch-report.json", "channel-economics-report.json" ->
                    orNotRun(outcome.gateEvidence().get(AssuranceArea.REGIONAL_CHANNEL));
            case "growth-risk-report.json", "batch-14-conformance-report.json" -> outcome.report();
            default -> Map.of();
        });
        return value;
    }

    private static Object orNotRun(Object value) {
        return value == null ? Map.of("status", "NOT_RUN") : value;
    }

    private Path evidence(Path target, Object value) throws IOException {
        return atomic(target, output -> json.writeValue(output, orNotRun(value)));
    }

    private Path jsonl(Path target, Collection<?> values) throws IOException {
        return atomic(target, raw -> {
            try (ZstdOutputStream zstd = new ZstdOutputStream(new BufferedOutputStream(raw))) {
                for (Object value : values) {
                    zstd.write(json.writeValueAsBytes(value));
                    zstd.write('\n');
                }
            }
        });
    }

    private Path atomic(Path target, IoWriter writer) throws IOException {
        assertSafeTarget(target);
        if (Files.exists(target, LinkOption.NOFOLLOW_LINKS))
            throw new FileAlreadyExistsException("Batch 14 growth evidence is append-only: " + target);
        Path temporary = Files.createTempFile(target.getParent(), ".batch14-", ".tmp");
        try {
            try (OutputStream output = Files.newOutputStream(temporary, StandardOpenOption.WRITE)) {
                writer.write(output);
            }
            try {
                Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE);
            } catch (AtomicMoveNotSupportedException ignored) {
                Files.move(temporary, target);
            }
            return target;
        } finally {
            Files.deleteIfExists(temporary);
        }
    }

    private static void secureDirectories(Path workspace) throws IOException {
        if (Files.exists(workspace, LinkOption.NOFOLLOW_LINKS) && Files.isSymbolicLink(workspace))
            throw new IOException("growth evidence workspace cannot be a symbolic link");
        if (!Files.exists(workspace, LinkOption.NOFOLLOW_LINKS)) Files.createDirectories(workspace);
        for (String directory : DIRECTORIES) {
            Path current = workspace;
            for (Path part : Path.of(directory)) {
                current = current.resolve(part);
                if (Files.exists(current, LinkOption.NOFOLLOW_LINKS)) {
                    if (Files.isSymbolicLink(current)
                            || !Files.isDirectory(current, LinkOption.NOFOLLOW_LINKS))
                        throw new IOException("unsafe growth artifact directory: " + current);
                } else {
                    Files.createDirectory(current);
                }
            }
        }
    }

    private static void assertSafeTarget(Path target) throws IOException {
        if (Files.isSymbolicLink(target.getParent()))
            throw new IOException("symbolic-link parent rejected: " + target.getParent());
    }

    private static void rejectRepository(Path workspace, Path repository) throws IOException {
        Path normalized = repository.toAbsolutePath().normalize();
        Path prospectiveWorkspace = prospectiveRealPath(workspace);
        Path realRepository = Files.exists(normalized) ? normalized.toRealPath() : normalized;
        if (workspace.equals(normalized) || workspace.startsWith(normalized)
                || prospectiveWorkspace.equals(realRepository)
                || prospectiveWorkspace.startsWith(realRepository))
            throw new IllegalArgumentException(
                    "growth evidence workspace cannot be inside the platform repository");
    }

    private static Path prospectiveRealPath(Path path) throws IOException {
        Path existing = path;
        Deque<Path> missing = new ArrayDeque<>();
        while (!Files.exists(existing)) {
            if (existing.getFileName() != null) missing.push(existing.getFileName());
            existing = existing.getParent();
            if (existing == null)
                throw new IOException("growth evidence workspace has no existing ancestor");
        }
        Path resolved = existing.toRealPath();
        while (!missing.isEmpty()) resolved = resolved.resolve(missing.pop());
        return resolved.normalize();
    }

    private static ObjectMapper configured(ObjectMapper mapper) {
        mapper.registerModule(new JavaTimeModule());
        mapper.setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
        mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
        return mapper;
    }

    @FunctionalInterface
    private interface IoWriter {
        void write(OutputStream output) throws IOException;
    }
}
