package io.elmos.securitycompliance;

import io.elmos.engine.api.EngineApi;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Function;

import static io.elmos.engine.api.EngineApi.*;

@Service
public final class SecurityComplianceEngineService {
    private record IdempotentResult(String fingerprint, JobResponse response) {}
    private final SecurityToolAdapterRegistry adapters;
    private final SecurityAuthorizationPolicy authorization;
    private final Map<String, JobResponse> jobs = new ConcurrentHashMap<>();
    private final Map<String, IdempotentResult> idempotency = new ConcurrentHashMap<>();

    public SecurityComplianceEngineService() { this(new SecurityToolAdapterRegistry(), new SecurityAuthorizationPolicy()); }
    SecurityComplianceEngineService(SecurityToolAdapterRegistry adapters, SecurityAuthorizationPolicy authorization) {
        this.adapters = Objects.requireNonNull(adapters); this.authorization = Objects.requireNonNull(authorization);
    }

    public Capabilities capabilities() {
        return new Capabilities("1.0", "ELMOS_SECURITY_COMPLIANCE", "1.0.0",
                List.of("CROSS_ENGINE_SECURITY"),
                List.of("JAVA", "DOTNET", "PYTHON", "FRONTEND_CLIENT", "DATABASE_DATA", "INFRASTRUCTURE", "COMPOSITE"),
                List.of("BASELINE", "STANDARD", "HIGH_ASSURANCE", "REGULATED", "CRITICAL_SYSTEM"),
                List.of("SPDX", "CYCLONEDX", "SLSA_ATTESTATION", "OSCAL"),
                List.of("SECURITY_DISCOVERY", "THREAT_MODELING", "CONTROL_BASELINING", "CONTROL_ASSESSING", "AUTHORIZATION_REVIEW", "CONTINUOUS_MONITORING"),
                List.of("NIST_CSF_2.0", "NIST_SP_800_207", "NIST_SP_800_207A", "NIST_SSDF_1.1", "OWASP_ASVS_5.0.0", "SLSA_1.2"),
                adapters.statusSummary(),
                List.of("SOURCE", "BUILD", "ARTIFACT", "DEPLOYMENT", "IDENTITY", "CLOUD", "RUNTIME", "DATA"),
                List.of("ESTATE", "IDENTITY", "SECRETS", "SUPPLY_CHAIN", "STATIC", "DYNAMIC", "VULNERABILITY", "CLOUD", "DATA", "THREAT", "CONTROL", "OSCAL", "AUTHORIZATION"),
                List.of("COVERAGE", "TENANT_ISOLATION", "EVIDENCE_FRESHNESS", "CONTROL_EFFECTIVENESS", "RISK", "OFFLINE_PACKAGE"),
                Map.of("network", "DENY_BY_DEFAULT", "runnerStatus", "NOT_CONFIGURED",
                        "activeTests", "EXPLICIT_TARGET_AUTHORIZATION_REQUIRED",
                        "secretEvidence", "FINGERPRINT_AND_REDACTED_REFERENCE_ONLY",
                        "riskAcceptance", "HUMAN_ONLY", "formalCertification", false));
    }

    public JobResponse scan(JobRequest request) {
        return once("scan", request, id -> failure(id, ErrorCode.SECURITY_TOOL_UNAVAILABLE,
                "approved tenant-scoped security adapters are not configured", "NOT_RUN"));
    }
    public JobResponse plan(JobRequest request) {
        return once("plan", request, id -> failure(id, ErrorCode.SECURITY_SCOPE_UNRESOLVED,
                "versioned estate, identities, boundaries, data flows, threats, catalogs, and profile are required", "INCONCLUSIVE"));
    }
    public JobResponse validate(JobRequest request) {
        return once("validate", request, id -> failure(id, ErrorCode.SECURITY_SCAN_INCOMPLETE,
                "independent coverage, findings, exposure, control, and evidence validation are required", "COVERAGE_INSUFFICIENT"));
    }
    public JobResponse executeStep(ExecuteStepRequest request) {
        require(request.organizationId(), "organizationId"); require(request.migrationRunId(), "migrationRunId");
        require(request.workspaceRef(), "workspaceRef"); require(request.idempotencyKey(), "idempotencyKey");
        return once("execute-step", request.organizationId(), request.idempotencyKey(), request.toString(), id -> {
            boolean active = request.stepDefinition().executorType() == ExecutorType.DAST
                    || request.stepDefinition().executorType() == ExecutorType.API_SECURITY;
            boolean approved = request.policy() != null && Boolean.TRUE.equals(request.policy().get("activeTestApproved"));
            ErrorCode code = active && !approved ? ErrorCode.SECURITY_TEST_AUTHORIZATION_REQUIRED : ErrorCode.SECURITY_TOOL_UNAVAILABLE;
            return failure(id, code, active && !approved
                    ? "active security testing requires target, environment, methods, limits, abort, cleanup, owner, and approval"
                    : "a capability-matched isolated adapter is required", "NOT_RUN");
        });
    }
    public SecurityModels.AuthorizationResult authorize(SecurityModels.AuthorizationRequest request) {
        return authorization.evaluate(request);
    }
    public JobResponse job(String organizationId, String jobId) {
        require(organizationId, "organizationId"); require(jobId, "jobId");
        return jobs.getOrDefault(organizationId + ":" + jobId,
                failure(jobId, ErrorCode.UNKNOWN, "job is not visible to this organization", "NOT_RUN"));
    }
    public JobResponse cancel(String organizationId, String jobId) {
        var existing = job(organizationId, jobId);
        if (existing.error() != null) return existing;
        if (List.of(JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED).contains(existing.status())) {
            return failure(jobId, ErrorCode.POLICY_BLOCKED, "terminal job cannot be cancelled", "NOT_RUN");
        }
        var cancelled = new JobResponse(existing.schemaVersion(), existing.jobId(), JobStatus.CANCELLED,
                existing.evidenceRefs(), existing.result(), null);
        jobs.put(organizationId + ":" + jobId, cancelled); return cancelled;
    }

    private JobResponse once(String operation, JobRequest request, Function<String, JobResponse> action) {
        require(request.organizationId(), "organizationId"); require(request.repositorySnapshotRef(), "repositorySnapshotRef");
        require(request.workspaceRef(), "workspaceRef"); require(request.profile(), "profile");
        require(request.correlationId(), "correlationId"); require(request.idempotencyKey(), "idempotencyKey");
        return once(operation, request.organizationId(), request.idempotencyKey(), request.toString(), action);
    }
    private JobResponse once(String operation, String organizationId, String key, String input, Function<String, JobResponse> action) {
        String scopedKey = organizationId + ":" + operation + ":" + key;
        String fingerprint = hash(operation + "\n" + input); var previous = idempotency.get(scopedKey);
        if (previous != null) {
            if (!previous.fingerprint().equals(fingerprint)) return failure(previous.response().jobId(), ErrorCode.POLICY_BLOCKED,
                    "idempotency key was reused with different input", "NOT_RUN");
            return previous.response();
        }
        String jobId = hash(scopedKey).substring(0, 24); JobResponse response = action.apply(jobId);
        idempotency.put(scopedKey, new IdempotentResult(fingerprint, response)); jobs.put(organizationId + ":" + jobId, response);
        return response;
    }
    private JobResponse failure(String jobId, ErrorCode code, String message, String status) {
        return new JobResponse("1.0", jobId, JobStatus.FAILED, List.of(),
                Map.of("configured", false, "executed", false, "customerTargetChanged", false,
                        "evidenceFabricated", false, "externalCertificationGranted", false,
                        "riskAcceptedByAgent", false, "externalStatus", status),
                new EngineError(code, message, false, List.of(), null, null,
                        "Configure the approved adapter and bind fresh independent evidence; route risk and formal authorization to qualified humans."));
    }
    private static String hash(String value) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8))); }
        catch (NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
    }
    private static void require(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required");
    }
}
