package io.elmos.mainframe;

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
import static io.elmos.mainframe.MainframeModels.*;

@Service
public final class MainframeEngineService {
    private record StoredJob(String organizationId, JobResponse response) {}
    private record IdempotentResult(String fingerprint, JobResponse response) {}
    private static final Set<ExecutorType> EXECUTORS = Set.of(
            ExecutorType.MAINFRAME_DISCOVERY, ExecutorType.MAINFRAME_ANALYSIS,
            ExecutorType.MAINFRAME_BUILD, ExecutorType.MAINFRAME_TEST,
            ExecutorType.MAINFRAME_PARALLEL_RUN, ExecutorType.MAINFRAME_CUTOVER);
    private final MainframeAdapterRegistry adapters;
    private final Map<String, StoredJob> jobs = new ConcurrentHashMap<>();
    private final Map<String, IdempotentResult> idempotency = new ConcurrentHashMap<>();

    public MainframeEngineService() { this(new MainframeAdapterRegistry()); }
    MainframeEngineService(MainframeAdapterRegistry adapters) { this.adapters = adapters; }

    public Capabilities capabilities() {
        return new Capabilities("1.0", "ELMOS_MAINFRAME", "1.0.0",
                List.of("COBOL", "PLI", "JCL", "REXX_INVENTORY", "ASSEMBLER_INVENTORY"),
                List.of("CICS", "IMS_TM", "IMS_DB", "DB2_ZOS", "VSAM", "MQ", "3270"),
                List.of("KEEP_ON_Z", "OPTIMIZE_ON_Z", "API_ENABLE", "MODULARIZE_ON_Z", "HYBRID_EXTRACT", "TRANSFORM_LANGUAGE", "REPLATFORM_RUNTIME", "REPLACE_PRODUCT", "RETIRE"),
                List.of("ESTATE_DISCOVERY", "COPYBOOK_ANALYSIS", "JCL_ANALYSIS", "BUSINESS_RULE_EXTRACTION", "API_ENABLEMENT", "REFACTOR", "TRANSFORM", "SEMANTIC_VALIDATION", "PARALLEL_RUN", "CUTOVER"),
                List.of("PDS", "PDSE", "SCM", "LOADLIB", "JCL", "COPYLIB"),
                List.of("DISCOVERY", "BUILD", "TEST", "DISTRIBUTED_ANALYSIS", "PARALLEL_COMPARATOR", "CUTOVER"),
                List.of("ZOSMF_REST", "SSH_ZOS_UNIX", "SCM_PRODUCT_ADAPTER", "APPLICATION_DISCOVERY_ADAPTER", "CUSTOM_AGENT"),
                List.of(),
                List.of("ESTATE_TWIN", "SOURCE_RUNTIME_MAP", "COBOL_SEMANTIC_GRAPH", "COPYBOOK_LAYOUT", "JCL_BATCH_DAG", "CICS_TRANSACTION_GRAPH", "IMS_HIERARCHY", "DB2_VSAM_GRAPH", "SEMANTIC_EQUIVALENCE", "PARALLEL_RUN"),
                List.of("LEASE_ENFORCEMENT", "DATASET_SCOPE", "SOURCE_RUNTIME_CORRELATION", "RULE_AUTHORITY", "SIDE_EFFECT_COMPARISON", "DATA_AUTHORITY", "DECOMMISSION_EVIDENCE"),
                Map.ofEntries(
                        Map.entry("adapterStatus", adapters.statusSummary()),
                        Map.entry("network", "ALLOWLIST_REQUIRED"),
                        Map.entry("discoveryReadOnly", true),
                        Map.entry("shortLivedJobLease", true),
                        Map.entry("datasetAllowlist", true),
                        Map.entry("controlPlaneExecution", false),
                        Map.entry("arbitraryJcl", false),
                        Map.entry("productionWritesDefault", "DENY"),
                        Map.entry("promotionRequiresIndependentApproval", true),
                        Map.entry("aiOutputsAuthoritative", false),
                        Map.entry("notRunCanPass", false)));
    }

    public JobResponse discover(JobRequest request) {
        return once("discover", request, id -> failure(request.organizationId(), id, ErrorCode.MAINFRAME_RUNNER_REQUIRED,
                "approved read-only z/OS discovery adapter is not configured", "NOT_RUN"));
    }
    public JobResponse scan(JobRequest request) { return discover(request); }
    public JobResponse analyze(JobRequest request) {
        return once("analyze", request, id -> failure(request.organizationId(), id, ErrorCode.MAINFRAME_ESTATE_INCOMPLETE,
                "immutable source, build, copybook, runtime and subsystem evidence is required", "INCONCLUSIVE"));
    }
    public JobResponse plan(JobRequest request) {
        return once("plan", request, id -> failure(request.organizationId(), id, ErrorCode.MAINFRAME_ESTATE_INCOMPLETE,
                "capability slices and separate online, batch and data-authority plans are required", "INCONCLUSIVE"));
    }
    public JobResponse transform(JobRequest request) {
        return once("transform", request, id -> failure(request.organizationId(), id, ErrorCode.MAINFRAME_SEMANTIC_DIFFERENCE,
                "transformation providers produce review-only candidates after modularization and baseline creation", "NOT_RUN"));
    }
    public JobResponse validate(JobRequest request) {
        return once("validate", request, id -> failure(request.organizationId(), id, ErrorCode.MAINFRAME_SEMANTIC_DIFFERENCE,
                "same-input, same-state semantic and side-effect evidence is required", "INCONCLUSIVE"));
    }

    public JobResponse execute(ExecuteStepRequest request) {
        require(request.organizationId(), "organizationId"); require(request.migrationRunId(), "migrationRunId");
        require(request.workspaceRef(), "workspaceRef"); require(request.sourceCommit(), "sourceCommit");
        require(request.idempotencyKey(), "idempotencyKey");
        return once("execute", request.organizationId(), request.idempotencyKey(), request.toString(), id -> {
            if (!EXECUTORS.contains(request.stepDefinition().executorType())) {
                return failure(request.organizationId(), id, ErrorCode.POLICY_BLOCKED, "executor is not a Mainframe runner", "NOT_RUN");
            }
            Map<String, Object> policy = request.policy() == null ? Map.of() : request.policy();
            if (!yes(policy, "mainframeJobLeaseApproved") || !yes(policy, "datasetScopeApproved")) {
                return failure(request.organizationId(), id, ErrorCode.MAINFRAME_LEASE_REQUIRED,
                        "short-lived mainframe job lease and dataset allowlist are required", "NOT_RUN");
            }
            if (yes(policy, "arbitraryJcl") || yes(policy, "controlPlaneExecution")) {
                return failure(request.organizationId(), id, ErrorCode.POLICY_BLOCKED,
                        "arbitrary JCL and control-plane mainframe execution are forbidden", "NOT_RUN");
            }
            if (yes(policy, "productionWriteRequested") && !yes(policy, "independentProductionApproval")) {
                return failure(request.organizationId(), id, ErrorCode.MAINFRAME_PRODUCTION_APPROVAL_REQUIRED,
                        "production dataset, loadlib, scheduler or route changes require independent approval", "NOT_RUN");
            }
            return failure(request.organizationId(), id, ErrorCode.MAINFRAME_RUNNER_REQUIRED,
                    "no approved Mainframe adapter is configured for this leased operation", "NOT_RUN");
        });
    }

    public RuleApprovalDecision approveRule(RuleApprovalRequest request) {
        if (request == null) throw new IllegalArgumentException("rule approval is required");
        require(request.ruleId(), "ruleId");
        boolean owner = request.businessOwner() != null && !request.businessOwner().isBlank();
        boolean authoritative = owner && request.evidence() == RuleEvidence.BUSINESS_APPROVED
                && request.sourceLinked() && request.runtimeLinked() && request.sideEffectsReviewed();
        List<String> reasons = authoritative ? List.of("BUSINESS_OWNER_APPROVED", "SOURCE_RUNTIME_AND_SIDE_EFFECTS_LINKED")
                : List.of("CANDIDATE_ONLY", "BUSINESS_APPROVAL_AND_TRACEABILITY_REQUIRED");
        return new RuleApprovalDecision(request.ruleId(), authoritative, reasons, Instant.now());
    }

    public JobResponse job(String organizationId, String jobId) {
        require(organizationId, "organizationId"); require(jobId, "jobId");
        StoredJob stored = jobs.get(jobId);
        if (stored == null || !stored.organizationId().equals(organizationId)) throw new IllegalArgumentException("job not found");
        return stored.response();
    }
    public JobResponse cancel(String organizationId, String jobId) {
        JobResponse current = job(organizationId, jobId);
        JobResponse cancelled = new JobResponse(current.schemaVersion(), current.jobId(), JobStatus.CANCELLED,
                current.evidenceRefs(), Map.of("externalStatus", "NOT_RUN", "customerCodeExecuted", false), null);
        jobs.put(jobId, new StoredJob(organizationId, cancelled)); return cancelled;
    }

    private JobResponse once(String action, JobRequest request, Function<String, JobResponse> work) {
        require(request.organizationId(), "organizationId"); require(request.repositorySnapshotRef(), "repositorySnapshotRef");
        require(request.workspaceRef(), "workspaceRef"); require(request.idempotencyKey(), "idempotencyKey");
        return once(action, request.organizationId(), request.idempotencyKey(), request.toString(), work);
    }
    private JobResponse once(String action, String organizationId, String key, String material, Function<String, JobResponse> work) {
        String scope = organizationId + ":" + action + ":" + key;
        String fingerprint = hash(material);
        IdempotentResult prior = idempotency.get(scope);
        if (prior != null) {
            if (!prior.fingerprint().equals(fingerprint)) throw new IllegalArgumentException("idempotency key reused with different request");
            return prior.response();
        }
        String jobId = "mf-" + hash(scope).substring(0, 20);
        JobResponse response = work.apply(jobId);
        idempotency.put(scope, new IdempotentResult(fingerprint, response));
        return response;
    }
    private JobResponse failure(String organizationId, String jobId, ErrorCode code, String message, String externalStatus) {
        EngineError error = new EngineError(code, message, false, List.of(), null, null,
                "configure an approved adapter or supply independently reviewed evidence");
        JobResponse response = new JobResponse("1.0", jobId, JobStatus.FAILED, List.of(),
                Map.of("externalStatus", externalStatus, "customerCodeExecuted", false,
                        "productionStateChanged", false, "evidenceFabricated", false), error);
        jobs.put(jobId, new StoredJob(organizationId, response)); return response;
    }
    private static boolean yes(Map<String, Object> policy, String key) { return Boolean.TRUE.equals(policy.get(key)); }
    private static void require(String value, String name) { if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required"); }
    private static String hash(String value) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8))); }
        catch (NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
    }
}
