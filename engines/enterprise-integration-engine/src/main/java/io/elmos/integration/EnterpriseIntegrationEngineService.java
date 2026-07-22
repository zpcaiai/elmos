package io.elmos.integration;

import io.elmos.engine.api.EngineApi;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Function;

import static io.elmos.engine.api.EngineApi.*;

@Service
public final class EnterpriseIntegrationEngineService {
    private record StoredJob(String organizationId, JobResponse response) {}
    private record IdempotentResult(String fingerprint, JobResponse response) {}
    private static final Set<ExecutorType> EXECUTORS = Set.of(
            ExecutorType.INTEGRATION_DISCOVERY, ExecutorType.INTEGRATION_ANALYSIS,
            ExecutorType.BROKER_VALIDATION, ExecutorType.API_GATEWAY_VALIDATION,
            ExecutorType.B2B_VALIDATION, ExecutorType.WORKFLOW_VALIDATION,
            ExecutorType.INTEGRATION_REPLAY, ExecutorType.INTEGRATION_CUTOVER);
    private final IntegrationAdapterRegistry adapters;
    private final Map<String, StoredJob> jobs = new ConcurrentHashMap<>();
    private final Map<String, IdempotentResult> idempotency = new ConcurrentHashMap<>();

    public EnterpriseIntegrationEngineService() { this(new IntegrationAdapterRegistry()); }
    EnterpriseIntegrationEngineService(IntegrationAdapterRegistry adapters) { this.adapters = adapters; }

    public Capabilities capabilities() {
        return new Capabilities("1.0", "ELMOS_ENTERPRISE_INTEGRATION", "1.0.0",
                List.of("ESB", "SOA", "IBM_MQ", "KAFKA", "RABBITMQ", "API_GATEWAY", "EDI", "MFT", "BPM"),
                List.of("IIB_APP_CONNECT", "TIBCO", "MULE", "OSB", "WEBMETHODS", "BIZTALK", "SAP_PI_PO", "JMS", "SOAP", "AS2"),
                List.of("KEEP_AND_HARDEN", "UPGRADE_PLATFORM", "MANAGED_EQUIVALENT", "API_ENABLE", "EVENT_ENABLE", "BROKER_REPLATFORM", "FLOW_DECOMPOSE", "WORKFLOW_EXTRACT", "DOMAIN_LOGIC_EXTRACT", "PARTNER_REPLATFORM", "REPLACE_PLATFORM", "RETIRE"),
                List.of("ESTATE_DISCOVERY", "CONTRACT_ANALYSIS", "ROUTE_ANALYSIS", "SCHEMA_GOVERNANCE", "MESSAGE_MIGRATION", "API_MODERNIZATION", "B2B_MODERNIZATION", "WORKFLOW_MODERNIZATION", "PARALLEL_RUN", "CUTOVER"),
                List.of("ASYNCAPI", "CLOUDEVENTS", "AVRO", "JSON_SCHEMA", "PROTOBUF", "XML_SCHEMA", "X12", "EDIFACT", "BPMN"),
                List.of("DISCOVERY", "BROKER_VALIDATION", "API_GATEWAY_VALIDATION", "B2B_TEST", "WORKFLOW", "REPLAY", "CUTOVER"),
                List.of("IBM_MQ", "KAFKA", "RABBITMQ", "SCHEMA_REGISTRY", "API_GATEWAY", "AS2", "SFTP", "BPMN"),
                List.of(),
                List.of("ESTATE_TWIN", "ROUTE_IR", "MESSAGE_CONTRACT", "DELIVERY_POLICY", "PRODUCER_CONSUMER_MATRIX", "PARTNER_MATRIX", "MESSAGE_LINEAGE", "FLOW_EQUIVALENCE", "CUTOVER_FRONTIER"),
                List.of("CONTRACT", "DELIVERY", "ORDERING", "IDEMPOTENCY", "DLQ", "PARTNER_ACK", "WORKFLOW_STATE", "REPLAY", "CUTOVER", "DECOMMISSION"),
                Map.ofEntries(
                        Map.entry("adapterStatus", adapters.statusSummary()),
                        Map.entry("network", "ALLOWLIST_REQUIRED"),
                        Map.entry("discoveryReadOnly", true),
                        Map.entry("shortLivedJobLease", true),
                        Map.entry("resourceScopeRequired", true),
                        Map.entry("controlPlaneExecution", false),
                        Map.entry("productionMutationDefault", "DENY"),
                        Map.entry("replayRequiresIndependentApproval", true),
                        Map.entry("partnerTestRequiresAuthorization", true),
                        Map.entry("workerModifiedGate", false),
                        Map.entry("messageLossAccepted", false),
                        Map.entry("notRunCanPass", false)));
    }

    public JobResponse scan(JobRequest request) {
        return once("scan", request, id -> failure(request.organizationId(), id, ErrorCode.INTEGRATION_RUNNER_REQUIRED,
                "approved read-only integration discovery adapter is not configured", "NOT_RUN"));
    }
    public JobResponse plan(JobRequest request) {
        return once("plan", request, id -> failure(request.organizationId(), id, ErrorCode.INTEGRATION_ESTATE_INCOMPLETE,
                "static configuration, runtime producer/consumer/partner usage, contracts and delivery semantics are required", "INCONCLUSIVE"));
    }
    public JobResponse validate(JobRequest request) {
        return once("validate", request, id -> failure(request.organizationId(), id, ErrorCode.DELIVERY_SEMANTICS_UNKNOWN,
                "contract, delivery, ordering, retry, side-effect and business-result evidence must be evaluated separately", "INCONCLUSIVE"));
    }

    public JobResponse executeStep(ExecuteStepRequest request) {
        require(request.organizationId(), "organizationId"); require(request.migrationRunId(), "migrationRunId");
        require(request.workspaceRef(), "workspaceRef"); require(request.sourceCommit(), "sourceCommit");
        require(request.idempotencyKey(), "idempotencyKey");
        if (request.stepDefinition() == null) throw new IllegalArgumentException("stepDefinition is required");
        return once("execute-step", request.organizationId(), request.idempotencyKey(), request.toString(), id -> {
            if (!EXECUTORS.contains(request.stepDefinition().executorType())) {
                return failure(request.organizationId(), id, ErrorCode.POLICY_BLOCKED, "executor is not an Enterprise Integration runner", "NOT_RUN");
            }
            Map<String, Object> policy = request.policy() == null ? Map.of() : request.policy();
            if (!yes(policy, "integrationJobLeaseApproved") || !yes(policy, "resourceScopeApproved")) {
                return failure(request.organizationId(), id, ErrorCode.INTEGRATION_LEASE_REQUIRED,
                        "short-lived integration job lease and endpoint, broker, partner or workflow scope are required", "NOT_RUN");
            }
            if (prohibited(policy)) {
                return failure(request.organizationId(), id, ErrorCode.POLICY_BLOCKED,
                        "queue purge, offset reset, topic deletion, certificate mutation, public route creation, producer switch and message loss are forbidden", "NOT_RUN");
            }
            if (request.stepDefinition().executorType() == ExecutorType.B2B_VALIDATION && !yes(policy, "partnerTestAuthorization")) {
                return failure(request.organizationId(), id, ErrorCode.PARTNER_TEST_AUTHORIZATION_REQUIRED,
                        "partner-specific test authorization is required", "NOT_RUN");
            }
            if (request.stepDefinition().executorType() == ExecutorType.INTEGRATION_REPLAY && !yes(policy, "replayAuthorization")) {
                return failure(request.organizationId(), id, ErrorCode.MESSAGE_REPLAY_NOT_AUTHORIZED,
                        "message range, rate, ordering, idempotency and side-effect replay approval are required", "NOT_RUN");
            }
            if (yes(policy, "productionMutationRequested") && !yes(policy, "independentProductionApproval")) {
                return failure(request.organizationId(), id, ErrorCode.INTEGRATION_PRODUCTION_APPROVAL_REQUIRED,
                        "production broker, gateway, partner, workflow or route changes require independent approval", "NOT_RUN");
            }
            return failure(request.organizationId(), id, ErrorCode.INTEGRATION_RUNNER_REQUIRED,
                    "no approved Enterprise Integration adapter is configured for this leased operation", "NOT_RUN");
        });
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
                current.evidenceRefs(), Map.of("externalStatus", "NOT_RUN", "customerCodeExecuted", false,
                "productionStateChanged", false, "workerModifiedGate", false), null);
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
        String jobId = "int-" + hash(scope).substring(0, 20);
        JobResponse response = work.apply(jobId);
        idempotency.put(scope, new IdempotentResult(fingerprint, response));
        return response;
    }
    private JobResponse failure(String organizationId, String jobId, ErrorCode code, String message, String externalStatus) {
        EngineError error = new EngineError(code, message, false, List.of(), null, null,
                "configure an approved adapter or supply independently reviewed contract and runtime evidence");
        JobResponse response = new JobResponse("1.0", jobId, JobStatus.FAILED, List.of(),
                Map.of("externalStatus", externalStatus, "customerCodeExecuted", false,
                        "productionStateChanged", false, "evidenceFabricated", false,
                        "workerModifiedGate", false, "messageLossAccepted", false), error);
        jobs.put(jobId, new StoredJob(organizationId, response)); return response;
    }
    private static boolean yes(Map<String, Object> policy, String key) { return Boolean.TRUE.equals(policy.get(key)); }
    private static boolean prohibited(Map<String, Object> policy) {
        return Set.of("purgeProductionQueue", "resetProductionOffset", "deleteTopic",
                "modifyPartnerCertificate", "replayProductionMessage", "createPublicGatewayRoute",
                "switchProducer", "acceptMessageLoss", "controlPlaneExecution").stream().anyMatch(key -> yes(policy, key));
    }
    private static void require(String value, String name) { if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required"); }
    private static String hash(String value) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8))); }
        catch (NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
    }
}
