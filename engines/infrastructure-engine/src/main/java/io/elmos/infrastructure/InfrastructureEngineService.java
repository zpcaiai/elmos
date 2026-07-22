package io.elmos.infrastructure;

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
public final class InfrastructureEngineService {
    private record IdempotentResult(String fingerprint, JobResponse response) {}

    private final ProviderRunnerRegistry runners;
    private final Map<String, JobResponse> jobs = new ConcurrentHashMap<>();
    private final Map<String, IdempotentResult> idempotency = new ConcurrentHashMap<>();

    public InfrastructureEngineService() { this(new ProviderRunnerRegistry()); }
    InfrastructureEngineService(ProviderRunnerRegistry runners) { this.runners = Objects.requireNonNull(runners); }

    public Capabilities capabilities() {
        return new Capabilities(
                "1.0", "ELMOS_INFRASTRUCTURE", "1.0.0",
                List.of("INFRASTRUCTURE"),
                List.of("BARE_METAL", "VMWARE", "KVM", "HYPER_V", "PRIVATE_CLOUD", "PUBLIC_CLOUD"),
                List.of("VM", "CONTAINER", "KUBERNETES", "SERVERLESS", "MANAGED_PLATFORM", "EDGE"),
                List.of("PACKER_COMPATIBLE", "ROOTLESS_BUILDKIT", "OPENTOFU", "HELM", "KUSTOMIZE"),
                List.of("VM_MODERNIZATION", "CONTAINER_KUBERNETES", "SERVERLESS_EVENT_DRIVEN", "CLOUD_GOVERNANCE"),
                List.of("COMPUTE", "NETWORK", "STORAGE", "IDENTITY", "SECRET", "LOAD_BALANCER", "REGISTRY", "KUBERNETES", "SERVERLESS", "OBSERVABILITY", "COST"),
                runners.all().keySet().stream().map(Enum::name).sorted().toList(),
                List.of("ON_PREM", "PRIVATE_CLOUD", "PUBLIC_CLOUD", "EDGE"),
                List.of("ESTATE_DISCOVERY", "WORKLOAD_PLACEMENT", "CONTAINERIZATION", "KUBERNETES", "SERVERLESS", "IAC", "NETWORK", "OBSERVABILITY", "FINOPS", "RESILIENCE", "MULTICLOUD", "CUTOVER"),
                List.of("POLICY", "COST", "SECURITY", "NETWORK_ENFORCEMENT", "SLO", "RESTORE", "PORTABILITY", "CUTOVER"),
                Map.of(
                        "network", "DENY_BY_DEFAULT",
                        "credentials", "SHORT_LIVED_PROVIDER_SCOPED_LEASE",
                        "discoveryPermissions", List.of("READ_INVENTORY", "READ_METRICS", "READ_CONFIGURATION", "READ_COST", "READ_LOG_METADATA"),
                        "writeSequence", List.of("PLAN", "POLICY", "COST", "SECURITY", "APPROVAL", "APPLY", "VALIDATION", "EVIDENCE"),
                        "productionWrites", "NAMED_APPROVAL_REQUIRED",
                        "providerExecution", "RUNNER_REQUIRED_FAIL_CLOSED",
                        "runnerStatus", "NOT_CONFIGURED"));
    }

    public JobResponse scan(JobRequest request) {
        return once("scan", request, jobId -> failure(jobId, ErrorCode.INFRASTRUCTURE_RUNNER_REQUIRED,
                "approved read-only infrastructure discovery Runner and provider-scoped credential lease are required"));
    }

    public JobResponse plan(JobRequest request) {
        return once("plan", request, jobId -> failure(jobId, ErrorCode.INFRASTRUCTURE_DISCOVERY_INCOMPLETE,
                "immutable estate, workload, dependency, utilization, ownership, region, and cost evidence are required"));
    }

    public JobResponse validate(JobRequest request) {
        return once("validate", request, jobId -> failure(jobId, ErrorCode.INFRASTRUCTURE_EVIDENCE_INCOMPLETE,
                "independent platform, network, SLO, cost, resilience, restore, and portability evidence are required"));
    }

    public JobResponse executeStep(ExecuteStepRequest request) {
        require(request.organizationId(), "organizationId"); require(request.migrationRunId(), "migrationRunId");
        require(request.workspaceRef(), "workspaceRef"); require(request.idempotencyKey(), "idempotencyKey");
        return once("execute-step", request.organizationId(), request.idempotencyKey(), request.toString(), jobId -> {
            boolean hasPlan = request.policy() != null && request.policy().get("immutablePlanRef") instanceof String value && !value.isBlank();
            boolean approved = request.policy() != null && request.policy().get("approvedBy") instanceof String value && !value.isBlank();
            ErrorCode code = !hasPlan ? ErrorCode.INFRASTRUCTURE_PLAN_REQUIRED
                    : !approved ? ErrorCode.INFRASTRUCTURE_APPROVAL_REQUIRED : ErrorCode.INFRASTRUCTURE_RUNNER_REQUIRED;
            return failure(jobId, code, "immutable plan, all policy gates, named approval, capability-matched Runner, scoped lease, and rollback are required");
        });
    }

    public JobResponse job(String organizationId, String jobId) {
        require(organizationId, "organizationId"); require(jobId, "jobId");
        return jobs.getOrDefault(organizationId + ":" + jobId,
                failure(jobId, ErrorCode.UNKNOWN, "job is not visible to this organization"));
    }

    public JobResponse cancel(String organizationId, String jobId) {
        var existing = job(organizationId, jobId);
        if (existing.error() != null) return existing;
        if (List.of(JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED).contains(existing.status())) {
            return failure(jobId, ErrorCode.POLICY_BLOCKED, "terminal job cannot be cancelled");
        }
        var cancelled = new JobResponse(existing.schemaVersion(), existing.jobId(), JobStatus.CANCELLED,
                existing.evidenceRefs(), existing.result(), null);
        jobs.put(organizationId + ":" + jobId, cancelled);
        return cancelled;
    }

    private JobResponse once(String operation, JobRequest request, Function<String, JobResponse> action) {
        require(request.organizationId(), "organizationId"); require(request.repositorySnapshotRef(), "repositorySnapshotRef");
        require(request.workspaceRef(), "workspaceRef"); require(request.profile(), "profile");
        require(request.correlationId(), "correlationId"); require(request.idempotencyKey(), "idempotencyKey");
        return once(operation, request.organizationId(), request.idempotencyKey(), request.toString(), action);
    }

    private JobResponse once(String operation, String organizationId, String key, String input, Function<String, JobResponse> action) {
        String scopedKey = organizationId + ":" + operation + ":" + key;
        String fingerprint = hash(operation + "\n" + input);
        var previous = idempotency.get(scopedKey);
        if (previous != null) {
            if (!previous.fingerprint().equals(fingerprint)) {
                return failure(previous.response().jobId(), ErrorCode.POLICY_BLOCKED, "idempotency key was reused with different input");
            }
            return previous.response();
        }
        String jobId = hash(scopedKey).substring(0, 24);
        JobResponse response = action.apply(jobId);
        idempotency.put(scopedKey, new IdempotentResult(fingerprint, response));
        jobs.put(organizationId + ":" + jobId, response);
        return response;
    }

    private JobResponse failure(String jobId, ErrorCode code, String message) {
        return new JobResponse("1.0", jobId, JobStatus.FAILED, List.of(),
                Map.of("configured", false, "executed", false, "providerOperationExecuted", false,
                        "customerInfrastructureChanged", false, "evidenceFabricated", false, "externalStatus", "NOT_RUN"),
                new EngineError(code, message, false, List.of(), null, null,
                        "Configure and approve the required Runner, provider lease, immutable plan, rollback, and independent evidence."));
    }

    private static String hash(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
    }

    private static void require(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required");
    }
}
