package io.elmos.testquality;

import io.elmos.engine.api.EngineApi;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Function;

import static io.elmos.engine.api.EngineApi.*;

@Service
public final class TestQualityEngineService {
    private record IdempotentResult(String fingerprint, JobResponse response) {}
    private static final Set<ExecutorType> TEST_EXECUTORS = Set.of(
            ExecutorType.UNIT_TEST, ExecutorType.INTEGRATION_TEST, ExecutorType.BROWSER_CLIENT_TEST,
            ExecutorType.DATA_ML_TEST, ExecutorType.PERFORMANCE_TEST, ExecutorType.MUTATION_TEST);
    private final TestToolAdapterRegistry adapters;
    private final Map<String, JobResponse> jobs = new ConcurrentHashMap<>();
    private final Map<String, IdempotentResult> idempotency = new ConcurrentHashMap<>();

    public TestQualityEngineService() { this(new TestToolAdapterRegistry()); }
    TestQualityEngineService(TestToolAdapterRegistry adapters) { this.adapters = adapters; }

    public Capabilities capabilities() {
        return new Capabilities("1.0", "ELMOS_TEST_QUALITY", "1.0.0",
                List.of("JAVA", "DOTNET", "PYTHON", "JAVASCRIPT", "TYPESCRIPT", "DATABASE", "DATA_ML", "INFRASTRUCTURE", "COMPOSITE"),
                List.of("UNIT", "COMPONENT", "INTEGRATION", "CONTRACT", "PROPERTY", "MUTATION", "E2E", "VISUAL", "ACCESSIBILITY", "DATA", "MODEL", "PERFORMANCE", "RESILIENCE"),
                List.of("TEST_DISCOVERY", "TEST_BASELINING", "QUALITY_RISK_MODELING", "TEST_PORTFOLIO_PLANNING", "CHARACTERIZATION_BUILDING", "TEST_MODERNIZING", "ENVIRONMENT_PREPARING", "TEST_EXECUTING", "FLAKY_ANALYZING", "TEST_EFFECTIVENESS_ANALYZING", "QUALITY_GATE_EVALUATING", "CONTINUOUS_VALIDATION"),
                List.of("TEST_DISCOVERY", "TEST_NORMALIZATION", "QUALITY_RISK", "TEST_GENERATION", "TEST_DATA", "SERVICE_VIRTUALIZATION", "FLAKY_GOVERNANCE", "TEST_IMPACT", "QUALITY_GATE", "CONTINUOUS_VALIDATION"),
                List.of("UNIT", "INTEGRATION", "BROWSER_CLIENT", "DATA_ML", "PERFORMANCE", "MUTATION"),
                List.of("ROOTLESS_EPHEMERAL", "NETWORK_DENY", "DIGEST_PINNED", "NO_PRODUCTION_SECRETS"),
                List.of("ROOTLESS_EPHEMERAL", "NAMESPACE_ISOLATED", "PERFORMANCE_DEDICATED"),
                adapters.statusSummary(), List.of(),
                List.of("DISCOVERY_RECONCILIATION", "RISK_COVERAGE", "ASSERTION_STRENGTH", "MUTATION_EFFECTIVENESS", "FLAKY_RELIABILITY", "ENVIRONMENT_FIDELITY", "EVIDENCE_FRESHNESS"),
                Map.of("network", "DENY_BY_DEFAULT", "runnerStatus", "NOT_CONFIGURED",
                        "namespaceIsolation", true, "shortLivedEnvironmentLease", true,
                        "shortLivedTestDataLease", true, "preserveFailingEvidence", true,
                        "workerCanModifyGate", false, "aiAutoPromotion", false,
                        "notRunCanPass", false, "productionSecretsAllowed", false));
    }

    public JobResponse discover(JobRequest request) {
        return once("discover", request, id -> failure(id, ErrorCode.TEST_QUALITY_RUNNER_REQUIRED,
                "approved discovery adapters are not configured", "NOT_RUN"));
    }
    public JobResponse scan(JobRequest request) { return discover(request); }
    public JobResponse plan(JobRequest request) {
        return once("plan", request, id -> failure(id, ErrorCode.TEST_DISCOVERY_INCOMPLETE,
                "a reconciled test estate, versioned quality risk model, coverage graph, and fresh baseline are required", "INCONCLUSIVE"));
    }
    public JobResponse generate(JobRequest request) {
        return once("generate", request, id -> failure(id, ErrorCode.AI_TEST_REVIEW_REQUIRED,
                "test generation requires a minimal context pack and produces review-only candidates", "NOT_RUN"));
    }
    public JobResponse evaluate(JobRequest request) {
        return once("evaluate", request, id -> failure(id, ErrorCode.TEST_QUALITY_GATE_FAILED,
                "independent current-artifact evidence is required; unknown and not-run dimensions cannot pass", "INCONCLUSIVE"));
    }
    public JobResponse validate(JobRequest request) { return evaluate(request); }
    public JobResponse execute(ExecuteStepRequest request) {
        require(request.organizationId(), "organizationId"); require(request.migrationRunId(), "migrationRunId");
        require(request.workspaceRef(), "workspaceRef"); require(request.sourceCommit(), "sourceCommit");
        require(request.idempotencyKey(), "idempotencyKey");
        return once("execute", request.organizationId(), request.idempotencyKey(), request.toString(), id -> {
            if (!TEST_EXECUTORS.contains(request.stepDefinition().executorType())) {
                return failure(id, ErrorCode.POLICY_BLOCKED, "executor is not a Test Quality runner", "NOT_RUN");
            }
            Map<String, Object> policy = request.policy() == null ? Map.of() : request.policy();
            boolean leases = Boolean.TRUE.equals(policy.get("environmentLeaseApproved"))
                    && Boolean.TRUE.equals(policy.get("testDataLeaseApproved"));
            if (!leases) return failure(id, ErrorCode.TEST_ENVIRONMENT_UNAVAILABLE,
                    "namespace-isolated environment and test data leases are required", "NOT_RUN");
            return failure(id, ErrorCode.TEST_QUALITY_RUNNER_REQUIRED,
                    "a capability-matched digest-pinned isolated runner is required", "NOT_RUN");
        });
    }
    public JobResponse executeStep(ExecuteStepRequest request) { return execute(request); }

    public QualityModels.PromotionDecision promote(QualityModels.PromotionRequest request) {
        require(request.candidateId(), "candidateId");
        var reasons = new java.util.ArrayList<String>();
        if (!request.compilePassed()) reasons.add("COMPILE_REQUIRED");
        if (!request.runPassed()) reasons.add("EXECUTION_REQUIRED");
        if (!request.failBeforeFixPassed()) reasons.add("FAIL_BEFORE_FIX_REQUIRED");
        if (!request.repeatable()) reasons.add("REPEATABILITY_REQUIRED");
        if (!request.mutationEffective()) reasons.add("MUTATION_EFFECTIVENESS_REQUIRED");
        if (!request.isolationPassed()) reasons.add("ISOLATION_REQUIRED");
        if (request.humanReviewer() == null || request.humanReviewer().isBlank()) reasons.add("HUMAN_REVIEW_REQUIRED");
        boolean promoted = reasons.isEmpty();
        return new QualityModels.PromotionDecision(request.candidateId(),
                promoted ? QualityModels.AiStatus.PROMOTED : QualityModels.AiStatus.REVIEW_REQUIRED,
                promoted, List.copyOf(reasons), Instant.now());
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
                Map.ofEntries(Map.entry("configured", false), Map.entry("executed", false),
                        Map.entry("customerCodeExecuted", false), Map.entry("customerEnvironmentChanged", false),
                        Map.entry("evidenceFabricated", false), Map.entry("workerModifiedGate", false),
                        Map.entry("aiTestAutoPromoted", false), Map.entry("flakyFailureHidden", false),
                        Map.entry("notRunTreatedAsPass", false), Map.entry("productionSecretsUsed", false),
                        Map.entry("externalStatus", status)),
                new EngineError(code, message, false, List.of(), null, null,
                        "Configure the approved isolated runner, environment and data leases, then bind fresh independent evidence to the current artifact."));
    }
    private static String hash(String value) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8))); }
        catch (NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
    }
    private static void require(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required");
    }
}
