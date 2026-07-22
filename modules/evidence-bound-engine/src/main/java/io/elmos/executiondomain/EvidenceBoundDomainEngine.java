package io.elmos.executiondomain;

import io.elmos.engine.api.EngineApi.*;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Function;

/** Shared fail-closed transport mechanics; domain policy remains in each independent engine definition. */
public final class EvidenceBoundDomainEngine {
    private record StoredJob(String organizationId, JobResponse response) {}
    private record IdempotentResult(String fingerprint, JobResponse response) {}

    private final DomainEngineDefinition definition;
    private final Map<String, StoredJob> jobs = new ConcurrentHashMap<>();
    private final Map<String, IdempotentResult> idempotency = new ConcurrentHashMap<>();

    public EvidenceBoundDomainEngine(DomainEngineDefinition definition) {
        this.definition = definition;
    }

    public Capabilities capabilities() {
        Map<String, String> adapterStatus = new LinkedHashMap<>();
        definition.adapters().forEach(adapter -> adapterStatus.put(adapter, "NOT_CONFIGURED"));
        return new Capabilities("1.0", definition.engineName(), "1.0.0",
                definition.domainKinds(), List.of("LEGACY", "CURRENT", "UNKNOWN"), definition.targetProfiles(),
                definition.artifactKinds(), definition.artifactKinds(), definition.projectFormats(),
                definition.runnerProfiles(), definition.adapters(), List.of(), definition.validationCapabilities(),
                Map.ofEntries(
                        Map.entry("adapterStatus", Map.copyOf(adapterStatus)),
                        Map.entry("stateMachines", definition.stateMachines()),
                        Map.entry("exceptionStates", definition.exceptionStates().stream().sorted().toList()),
                        Map.entry("network", "ALLOWLIST_REQUIRED"),
                        Map.entry("discoveryReadOnly", true),
                        Map.entry("shortLivedJobLease", true),
                        Map.entry("environmentScopeRequired", true),
                        Map.entry("controlPlaneExecution", false),
                        Map.entry("productionMutationDefault", "DENY"),
                        Map.entry("humanDecisionAutoGrant", false),
                        Map.entry("workerModifiedGate", false),
                        Map.entry("notRunCanPass", false)));
    }

    public boolean transitionAllowed(String machine, String from, String to) {
        require(machine, "machine"); require(from, "from"); require(to, "to");
        if (definition.exceptionStates().contains(from) || definition.exceptionStates().contains(to)) return false;
        List<String> states = definition.stateMachines().get(machine);
        if (states == null) throw new IllegalArgumentException("unknown state machine: " + machine);
        int position = states.indexOf(from);
        return position >= 0 && position + 1 < states.size() && states.get(position + 1).equals(to);
    }

    public JobResponse discover(JobRequest request) {
        return once("discover", request, id -> failure(request.organizationId(), id, definition.runnerRequired(),
                "approved read-only provider adapter is not configured", "NOT_RUN"));
    }

    public JobResponse plan(JobRequest request) {
        return once("plan", request, id -> failure(request.organizationId(), id, definition.estateIncomplete(),
                "estate, ownership, runtime, dependency and business evidence are incomplete", "INCONCLUSIVE"));
    }

    public JobResponse evaluate(String action, JobRequest request) {
        return once(action, request, id -> failure(request.organizationId(), id, definition.estateIncomplete(),
                "independent current evidence is required for this decision", "INCONCLUSIVE"));
    }

    public JobResponse executeStep(ExecuteStepRequest request) {
        return execute("execute-step", request);
    }

    public JobResponse execute(String action, ExecuteStepRequest request) {
        require(request.organizationId(), "organizationId");
        require(request.migrationRunId(), "migrationRunId");
        require(request.workspaceRef(), "workspaceRef");
        require(request.sourceCommit(), "sourceCommit");
        require(request.idempotencyKey(), "idempotencyKey");
        if (request.stepDefinition() == null) throw new IllegalArgumentException("stepDefinition is required");
        return once(action, request.organizationId(), request.idempotencyKey(), request.toString(), id -> {
            if (!definition.executors().contains(request.stepDefinition().executorType())) {
                return failure(request.organizationId(), id, ErrorCode.POLICY_BLOCKED,
                        "executor is outside this engine's bounded domain", "NOT_RUN");
            }
            Map<String, Object> policy = request.policy() == null ? Map.of() : request.policy();
            if (!yes(policy, "jobLeaseApproved") || !yes(policy, "environmentScopeApproved")) {
                return failure(request.organizationId(), id, definition.leaseRequired(),
                        "short-lived job lease and exact environment scope are required", "NOT_RUN");
            }
            if (definition.prohibitedPolicyKeys().stream().anyMatch(key -> yes(policy, key))) {
                return failure(request.organizationId(), id, ErrorCode.POLICY_BLOCKED,
                        "requested operation is prohibited by the domain safety boundary", "NOT_RUN");
            }
            DomainEngineDefinition.AuthorizationRule rule = definition.authorizationRules()
                    .get(request.stepDefinition().executorType());
            if (rule != null && !yes(policy, rule.policyKey())) {
                return failure(request.organizationId(), id, rule.errorCode(), rule.message(), "NOT_RUN");
            }
            if (yes(policy, "productionMutationRequested") && !yes(policy, "independentProductionApproval")) {
                return failure(request.organizationId(), id, definition.productionApprovalRequired(),
                        "production mutation requires independent approval", "NOT_RUN");
            }
            return failure(request.organizationId(), id, definition.runnerRequired(),
                    "no approved provider adapter is configured for this leased operation", "NOT_RUN");
        });
    }

    public JobResponse job(String organizationId, String jobId) {
        require(organizationId, "organizationId"); require(jobId, "jobId");
        StoredJob stored = jobs.get(jobId);
        if (stored == null || !stored.organizationId().equals(organizationId)) {
            throw new IllegalArgumentException("job not found");
        }
        return stored.response();
    }

    public JobResponse cancel(String organizationId, String jobId) {
        JobResponse current = job(organizationId, jobId);
        JobResponse cancelled = new JobResponse(current.schemaVersion(), current.jobId(), JobStatus.CANCELLED,
                current.evidenceRefs(), result("NOT_RUN"), null);
        jobs.put(jobId, new StoredJob(organizationId, cancelled));
        return cancelled;
    }

    private JobResponse once(String action, JobRequest request, Function<String, JobResponse> work) {
        require(request.organizationId(), "organizationId");
        require(request.repositorySnapshotRef(), "repositorySnapshotRef");
        require(request.workspaceRef(), "workspaceRef");
        require(request.idempotencyKey(), "idempotencyKey");
        return once(action, request.organizationId(), request.idempotencyKey(), request.toString(), work);
    }

    private JobResponse once(String action, String organizationId, String key, String material,
                             Function<String, JobResponse> work) {
        String scope = organizationId + ":" + definition.engineName() + ":" + action + ":" + key;
        String fingerprint = hash(material);
        IdempotentResult prior = idempotency.get(scope);
        if (prior != null) {
            if (!prior.fingerprint().equals(fingerprint)) {
                throw new IllegalArgumentException("idempotency key reused with different request");
            }
            return prior.response();
        }
        String jobId = definition.engineName().toLowerCase().replace("elmos_", "") + "-" + hash(scope).substring(0, 20);
        JobResponse response = work.apply(jobId);
        idempotency.put(scope, new IdempotentResult(fingerprint, response));
        return response;
    }

    private JobResponse failure(String organizationId, String jobId, ErrorCode code, String message, String externalStatus) {
        EngineError error = new EngineError(code, message, false, List.of(), null, null,
                "configure an approved provider or supply independently reviewed evidence");
        JobResponse response = new JobResponse("1.0", jobId, JobStatus.FAILED, List.of(), result(externalStatus), error);
        jobs.put(jobId, new StoredJob(organizationId, response));
        return response;
    }

    private static Map<String, Object> result(String externalStatus) {
        return Map.ofEntries(
                Map.entry("externalStatus", externalStatus),
                Map.entry("customerSystemAccessed", false),
                Map.entry("externalOperationExecuted", false),
                Map.entry("productionStateChanged", false),
                Map.entry("evidenceFabricated", false),
                Map.entry("riskAccepted", false),
                Map.entry("humanDecisionGranted", false),
                Map.entry("workerModifiedGate", false));
    }

    private static boolean yes(Map<String, Object> policy, String key) {
        return Boolean.TRUE.equals(policy.get(key));
    }

    private static void require(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required");
    }

    private static String hash(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(impossible);
        }
    }
}
