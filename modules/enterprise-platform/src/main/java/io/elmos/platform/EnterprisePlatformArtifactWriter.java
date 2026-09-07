package io.elmos.platform;

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

import static io.elmos.platform.EnterprisePlatformModels.*;

/** Writes append-only Batch 12 enterprise-platform evidence outside the platform repository. */
public final class EnterprisePlatformArtifactWriter {
    private static final List<String> DIRECTORIES = List.of(
            "enterprise-platform/control-plane/tenant", "enterprise-platform/control-plane/organization",
            "enterprise-platform/control-plane/identity", "enterprise-platform/control-plane/authorization",
            "enterprise-platform/control-plane/policy", "enterprise-platform/control-plane/approval",
            "enterprise-platform/control-plane/workflow", "enterprise-platform/control-plane/quota",
            "enterprise-platform/control-plane/billing", "enterprise-platform/control-plane/audit",
            "enterprise-platform/control-plane/retention",
            "enterprise-platform/execution-plane/scheduler", "enterprise-platform/execution-plane/runner-manager",
            "enterprise-platform/execution-plane/runner-agent", "enterprise-platform/execution-plane/sandbox",
            "enterprise-platform/execution-plane/secret-broker", "enterprise-platform/execution-plane/artifact-relay",
            "enterprise-platform/model-plane/gateway", "enterprise-platform/model-plane/registry",
            "enterprise-platform/model-plane/router", "enterprise-platform/model-plane/policies",
            "enterprise-platform/model-plane/metering", "enterprise-platform/model-plane/local-models",
            "enterprise-platform/artifact-plane/registry", "enterprise-platform/artifact-plane/provenance",
            "enterprise-platform/artifact-plane/evidence", "enterprise-platform/artifact-plane/sbom",
            "enterprise-platform/artifact-plane/signatures", "enterprise-platform/artifact-plane/export",
            "enterprise-platform/trust-plane/workload-identity", "enterprise-platform/trust-plane/kms",
            "enterprise-platform/trust-plane/hsm", "enterprise-platform/trust-plane/certificates",
            "enterprise-platform/trust-plane/signing", "enterprise-platform/integrations/github",
            "enterprise-platform/integrations/gitlab", "enterprise-platform/integrations/bitbucket",
            "enterprise-platform/integrations/oidc", "enterprise-platform/integrations/saml",
            "enterprise-platform/integrations/scim", "enterprise-platform/integrations/ci",
            "enterprise-platform/deployments/saas", "enterprise-platform/deployments/dedicated",
            "enterprise-platform/deployments/hybrid-runner", "enterprise-platform/deployments/self-hosted",
            "enterprise-platform/deployments/air-gapped", "enterprise-platform/offline/bundles",
            "enterprise-platform/offline/registry", "enterprise-platform/offline/models",
            "enterprise-platform/offline/licenses", "enterprise-platform/offline/updates",
            "enterprise-platform/offline/vulnerability-feeds", "enterprise-platform/observability/telemetry-contract",
            "enterprise-platform/observability/dashboards", "enterprise-platform/observability/alerts",
            "enterprise-platform/observability/runbooks", "enterprise-platform/tests/tenancy",
            "enterprise-platform/tests/identity", "enterprise-platform/tests/policy",
            "enterprise-platform/tests/runner", "enterprise-platform/tests/model-gateway",
            "enterprise-platform/tests/billing", "enterprise-platform/tests/audit",
            "enterprise-platform/tests/retention", "enterprise-platform/tests/offline",
            "enterprise-platform/reports");
    private static final List<String> REPORTS = List.of(
            "tenant-isolation-report.json", "identity-security-report.json", "authorization-report.json",
            "private-runner-report.json", "model-governance-report.json", "quota-metering-report.json",
            "billing-reconciliation-report.json", "audit-integrity-report.json", "data-governance-report.json",
            "self-hosted-report.json", "air-gapped-report.json", "batch-12-conformance-report.json");

    private final ObjectMapper json = configured(new ObjectMapper());
    private final ObjectMapper yaml = configured(new ObjectMapper(new YAMLFactory()));

    public Map<String, Path> write(Outcome outcome) throws IOException {
        Objects.requireNonNull(outcome, "outcome");
        Path workspace = outcome.request().artifactWorkspace().toAbsolutePath().normalize();
        rejectRepository(workspace, outcome.request().platformRepositoryPath());
        secureDirectories(workspace);
        Path root = workspace.resolve("enterprise-platform");
        Map<String, Path> written = new LinkedHashMap<>();
        written.put("manifest", atomic(root.resolve("control-plane/platform-manifest.yaml"),
                output -> yaml.writeValue(output, manifest(outcome))));
        written.put("control-model", atomic(root.resolve("control-plane/enterprise-platform-control-model.json"),
                output -> json.writeValue(output, controlModel(outcome))));
        written.put("gate-results", atomic(root.resolve("control-plane/batch-12-gate-results.json"),
                output -> json.writeValue(output, outcome.report())));
        written.put("tenants", jsonl(root.resolve("control-plane/tenant/tenant-profiles.jsonl.zst"), outcome.request().tenants()));
        written.put("deployments", jsonl(root.resolve("deployments/deployment-profiles.jsonl.zst"), outcome.request().deployments()));
        written.put("capabilities", jsonl(root.resolve("control-plane/capability-bindings.jsonl.zst"), outcome.request().capabilities()));
        written.put("tenancy-identity-evidence", evidence(root.resolve("artifact-plane/evidence/tenancy-identity.json"), outcome.tenancyIdentity()));
        written.put("authorization-audit-evidence", evidence(root.resolve("artifact-plane/evidence/authorization-audit.json"), outcome.authorizationAudit()));
        written.put("runner-security-evidence", evidence(root.resolve("artifact-plane/evidence/runner-security.json"), outcome.runnerSecurity()));
        written.put("model-cost-evidence", evidence(root.resolve("artifact-plane/evidence/model-cost.json"), outcome.modelCost()));
        written.put("data-governance-evidence", evidence(root.resolve("artifact-plane/evidence/data-governance.json"), outcome.dataGovernance()));
        written.put("deployment-evidence", evidence(root.resolve("artifact-plane/evidence/deployment.json"), outcome.deployment()));
        written.put("enterprise-acceptance-evidence", evidence(root.resolve("artifact-plane/evidence/enterprise-acceptance.json"), outcome.acceptance()));
        written.put("enterprise-evidence-pack", atomic(root.resolve("artifact-plane/evidence/enterprise-evidence-pack.json"),
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
        value.put("batch", 12); value.put("assessment_run_id", request.assessmentRunId());
        value.put("platform", request.platform()); value.put("tenants", request.tenants());
        value.put("deployments", request.deployments()); value.put("capabilities", request.capabilities());
        value.put("policy", request.policy()); value.put("observed_at", request.observedAt());
        value.put("production_operation_executed", false);
        return value;
    }

    private static Map<String, Object> controlModel(Outcome outcome) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("protocol", "ELMOS-EPCM"); value.put("version", "1.0"); value.put("batch", 12);
        value.put("gates", Gate.values()); value.put("deployment_modes", DeploymentMode.values());
        value.put("highest_gate", outcome.report().gate());
        value.put("tenant_default_deny", true); value.put("control_plane_executes_customer_code", false);
        value.put("control_plane_executes_production_operations", false);
        return value;
    }

    private static Map<String, Object> evidencePack(Outcome outcome) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("platform_version", outcome.request().platform().platformVersion());
        value.put("platform_digest", outcome.request().platform().artifactDigest());
        value.put("tenancy_identity", orNotRun(outcome.tenancyIdentity()));
        value.put("authorization_audit", orNotRun(outcome.authorizationAudit()));
        value.put("runner_security", orNotRun(outcome.runnerSecurity()));
        value.put("model_cost", orNotRun(outcome.modelCost()));
        value.put("data_governance", orNotRun(outcome.dataGovernance()));
        value.put("deployments", orNotRun(outcome.deployment()));
        value.put("acceptance", orNotRun(outcome.acceptance()));
        value.put("conformance", outcome.report());
        return value;
    }

    private static Object reportPayload(String report, Outcome outcome) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("report", report); value.put("platform_version", outcome.request().platform().platformVersion());
        value.put("assessment_run_id", outcome.request().assessmentRunId()); value.put("conformance", outcome.report());
        value.put("domain_evidence", switch (report) {
            case "tenant-isolation-report.json", "identity-security-report.json" -> orNotRun(outcome.tenancyIdentity());
            case "authorization-report.json", "audit-integrity-report.json" -> orNotRun(outcome.authorizationAudit());
            case "private-runner-report.json" -> orNotRun(outcome.runnerSecurity());
            case "model-governance-report.json", "quota-metering-report.json", "billing-reconciliation-report.json" -> orNotRun(outcome.modelCost());
            case "data-governance-report.json" -> orNotRun(outcome.dataGovernance());
            case "self-hosted-report.json", "air-gapped-report.json" -> orNotRun(outcome.deployment());
            case "batch-12-conformance-report.json" -> outcome.report();
            default -> Map.of();
        });
        return value;
    }

    private static Object orNotRun(Object value) { return value == null ? Map.of("status", "NOT_RUN") : value; }

    private Path evidence(Path target, EvidenceEnvelope value) throws IOException {
        return atomic(target, output -> json.writeValue(output, orNotRun(value)));
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
            throw new FileAlreadyExistsException("Batch 12 evidence is append-only: " + target);
        Path temporary = Files.createTempFile(target.getParent(), ".batch12-", ".tmp");
        try {
            try (OutputStream output = Files.newOutputStream(temporary, StandardOpenOption.WRITE)) { writer.write(output); }
            try { Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE); }
            catch (AtomicMoveNotSupportedException ignored) { Files.move(temporary, target); }
            return target;
        } finally { Files.deleteIfExists(temporary); }
    }

    private static void secureDirectories(Path workspace) throws IOException {
        if (Files.exists(workspace, LinkOption.NOFOLLOW_LINKS) && Files.isSymbolicLink(workspace))
            throw new IOException("enterprise evidence workspace cannot be a symbolic link");
        if (!Files.exists(workspace, LinkOption.NOFOLLOW_LINKS)) Files.createDirectories(workspace);
        for (String directory : DIRECTORIES) {
            Path current = workspace;
            for (Path part : Path.of(directory)) {
                current = current.resolve(part);
                if (Files.exists(current, LinkOption.NOFOLLOW_LINKS)) {
                    if (Files.isSymbolicLink(current) || !Files.isDirectory(current, LinkOption.NOFOLLOW_LINKS))
                        throw new IOException("unsafe enterprise artifact directory: " + current);
                } else Files.createDirectory(current);
            }
        }
    }

    private static void assertSafeTarget(Path target) throws IOException {
        if (Files.isSymbolicLink(target.getParent()))
            throw new IOException("symbolic-link parent rejected: " + target.getParent());
    }

    private static void rejectRepository(Path workspace, Path repository) throws IOException {
        Path normalized = repository.toAbsolutePath().normalize();
        boolean insideDeclaredPath = workspace.equals(normalized) || workspace.startsWith(normalized);
        Path prospectiveWorkspace = prospectiveRealPath(workspace);
        Path realRepository = Files.exists(normalized) ? normalized.toRealPath() : normalized;
        boolean insideRealPath = prospectiveWorkspace.equals(realRepository)
                || prospectiveWorkspace.startsWith(realRepository);
        if (insideDeclaredPath || insideRealPath)
            throw new IllegalArgumentException("enterprise evidence workspace cannot be inside the platform repository");
    }

    private static Path prospectiveRealPath(Path path) throws IOException {
        Path existing = path;
        Deque<Path> missing = new ArrayDeque<>();
        while (!Files.exists(existing)) {
            if (existing.getFileName() != null) missing.push(existing.getFileName());
            existing = existing.getParent();
            if (existing == null) throw new IOException("enterprise evidence workspace has no existing ancestor");
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

    @FunctionalInterface private interface IoWriter { void write(OutputStream output) throws IOException; }
}
