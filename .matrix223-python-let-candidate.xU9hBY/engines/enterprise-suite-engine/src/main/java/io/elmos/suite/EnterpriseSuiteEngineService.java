package io.elmos.suite;

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
public final class EnterpriseSuiteEngineService {
    private record StoredJob(String organizationId, JobResponse response) {}
    private record IdempotentResult(String fingerprint, JobResponse response) {}
    private static final Set<ExecutorType> EXECUTORS = Set.of(
            ExecutorType.SUITE_DISCOVERY, ExecutorType.SUITE_ANALYSIS,
            ExecutorType.SAP_VALIDATION, ExecutorType.ORACLE_VALIDATION,
            ExecutorType.DYNAMICS_VALIDATION, ExecutorType.SALESFORCE_VALIDATION,
            ExecutorType.MASTER_DATA_VALIDATION, ExecutorType.SUITE_DATA_MIGRATION,
            ExecutorType.BUSINESS_PROCESS_VALIDATION,
            ExecutorType.SUITE_INTEGRATION_VALIDATION, ExecutorType.SUITE_CUTOVER);
    private final SuiteAdapterRegistry adapters;
    private final Map<String, StoredJob> jobs = new ConcurrentHashMap<>();
    private final Map<String, IdempotentResult> idempotency = new ConcurrentHashMap<>();

    public EnterpriseSuiteEngineService() { this(new SuiteAdapterRegistry()); }
    EnterpriseSuiteEngineService(SuiteAdapterRegistry adapters) { this.adapters = adapters; }

    public Capabilities capabilities() {
        return new Capabilities("1.0", "ELMOS_ENTERPRISE_SUITE", "1.0.0",
                List.of("SAP_ECC", "SAP_S4HANA", "ORACLE_EBS", "ORACLE_FUSION", "DYNAMICS_365", "DATAVERSE", "POWER_PLATFORM", "SALESFORCE"),
                List.of("ECC", "S4HANA", "EBS_12_2", "FUSION_CLOUD", "DYNAMICS_365", "SALESFORCE_ORG"),
                List.of("KEEP_AND_GOVERN", "TECHNICAL_UPGRADE", "SYSTEM_CONVERSION", "GREENFIELD_IMPLEMENTATION", "SELECTIVE_DATA_TRANSITION", "CLOUD_REIMPLEMENTATION", "MODULE_REPLACEMENT", "COMPOSABLE_SUITE", "DUAL_SUITE_COEXISTENCE", "FULL_REPLACEMENT", "RETIRE"),
                List.of("TRANSPORT", "SOLUTION", "METADATA_PACKAGE", "DATA_MIGRATION_PACKAGE"),
                List.of("SAP_TRANSPORT", "ORACLE_CONFIGURATION_PACKAGE", "DYNAMICS_SOLUTION", "SALESFORCE_PACKAGE"),
                List.of("SUITE_ESTATE", "BUSINESS_PROCESS_GRAPH", "MASTER_DATA_MODEL", "CLEAN_CORE_ASSESSMENT", "COMPOSITE_CHANGE_SET"),
                List.of("DISCOVERY", "SAP", "ORACLE", "DYNAMICS", "SALESFORCE", "MASTER_DATA", "DATA_MIGRATION", "PROCESS_VALIDATION", "INTEGRATION_TEST", "CUTOVER"),
                List.of("SAP", "ORACLE_EBS", "ORACLE_FUSION", "DYNAMICS", "DATAVERSE", "SALESFORCE", "PROCESS_MINING", "MDM", "ARCHIVE"),
                List.of(),
                List.of("CONFIGURATION", "CUSTOMIZATION", "CLEAN_CORE", "MASTER_DATA", "PROCESS", "FINANCIAL", "INVENTORY", "ROLE_SOD", "REPORT_SECURITY", "CUTOVER", "DECOMMISSION"),
                Map.ofEntries(
                        Map.entry("adapterStatus", adapters.statusSummary()),
                        Map.entry("network", "ALLOWLIST_REQUIRED"),
                        Map.entry("discoveryReadOnly", true),
                        Map.entry("shortLivedJobLease", true),
                        Map.entry("environmentScopeRequired", true),
                        Map.entry("controlPlaneExecution", false),
                        Map.entry("jobStatePersistence", "EPHEMERAL_PROCESS_LOCAL"),
                        Map.entry("durableStateAuthority", "ELMOS_CONTROL_PLANE"),
                        Map.entry("restartRecovery", "NOT_SUPPORTED_BY_WORKER"),
                        Map.entry("productionMutationDefault", "DENY"),
                        Map.entry("processDifferenceAutoAccept", false),
                        Map.entry("financialDifferenceAutoAccept", false),
                        Map.entry("sodConflictAutoAccept", false),
                        Map.entry("workerModifiedGate", false),
                        Map.entry("notRunCanPass", false)));
    }

    public JobResponse scan(JobRequest request) {
        return once("scan", request, id -> failure(request.organizationId(), id, ErrorCode.SUITE_RUNNER_REQUIRED,
                "approved read-only suite metadata adapter is not configured", "NOT_RUN"));
    }
    public JobResponse plan(JobRequest request) {
        return once("plan", request, id -> failure(request.organizationId(), id, ErrorCode.SUITE_ESTATE_INCOMPLETE,
                "suite configuration, extensions, process variants, master data, roles, reports, integrations and usage are required", "INCONCLUSIVE"));
    }
    public JobResponse validate(JobRequest request) {
        return once("validate", request, id -> failure(request.organizationId(), id, ErrorCode.BUSINESS_PROCESS_UNKNOWN,
                "business, financial, inventory, security, report and integration outcomes require independently approved evidence", "INCONCLUSIVE"));
    }

    public JobResponse executeStep(ExecuteStepRequest request) {
        require(request.organizationId(), "organizationId"); require(request.migrationRunId(), "migrationRunId");
        require(request.workspaceRef(), "workspaceRef"); require(request.sourceCommit(), "sourceCommit");
        require(request.idempotencyKey(), "idempotencyKey");
        if (request.stepDefinition() == null) throw new IllegalArgumentException("stepDefinition is required");
        return once("execute-step", request.organizationId(), request.idempotencyKey(), EngineApi.idempotencyMaterial(request), id -> {
            if (!EXECUTORS.contains(request.stepDefinition().executorType())) {
                return failure(request.organizationId(), id, ErrorCode.POLICY_BLOCKED, "executor is not an Enterprise Suite runner", "NOT_RUN");
            }
            Map<String, Object> policy = request.policy() == null ? Map.of() : request.policy();
            if (!yes(policy, "suiteJobLeaseApproved") || !yes(policy, "environmentScopeApproved")) {
                return failure(request.organizationId(), id, ErrorCode.SUITE_LEASE_REQUIRED,
                        "short-lived suite job lease and exact environment scope are required", "NOT_RUN");
            }
            if (prohibited(policy)) {
                return failure(request.organizationId(), id, ErrorCode.POLICY_BLOCKED,
                        "production configuration, transports, solutions, permissions, data deletion, automatic difference acceptance and automatic cutover are forbidden", "NOT_RUN");
            }
            if (request.stepDefinition().executorType() == ExecutorType.BUSINESS_PROCESS_VALIDATION
                    && !yes(policy, "suiteSandboxAuthorization")) {
                return failure(request.organizationId(), id, ErrorCode.SUITE_SANDBOX_AUTHORIZATION_REQUIRED,
                        "an approved synthetic company, data set, workflow users and virtualized integration scope are required", "NOT_RUN");
            }
            if (request.stepDefinition().executorType() == ExecutorType.SUITE_DATA_MIGRATION
                    && !yes(policy, "dataMigrationAuthorization")) {
                return failure(request.organizationId(), id, ErrorCode.SUITE_DATA_MIGRATION_AUTHORIZATION_REQUIRED,
                        "object, company, wave, reject handling and reconciliation authorization are required", "NOT_RUN");
            }
            if ((yes(policy, "productionMutationRequested") || yes(policy, "masterDataAuthoritySwitchRequested"))
                    && !yes(policy, "independentProductionApproval")) {
                return failure(request.organizationId(), id, ErrorCode.SUITE_PRODUCTION_APPROVAL_REQUIRED,
                        "production suite or master-data authority changes require independent approval", "NOT_RUN");
            }
            return failure(request.organizationId(), id, ErrorCode.SUITE_RUNNER_REQUIRED,
                    "no approved Enterprise Suite adapter is configured for this leased operation", "NOT_RUN");
        });
    }

    public JobResponse job(String organizationId, String jobId) {
        require(organizationId, "organizationId"); require(jobId, "jobId");
        StoredJob stored = jobs.get(jobId);
        if (stored == null || !stored.organizationId().equals(organizationId)) throw new EngineApi.JobNotFoundException(jobId);
        return stored.response();
    }
    public JobResponse cancel(String organizationId, String jobId) {
        JobResponse current = job(organizationId, jobId);
        if (EngineApi.isTerminal(current.status())) throw new EngineApi.JobConflictException(jobId);
        JobResponse cancelled = new JobResponse(current.schemaVersion(), current.jobId(), JobStatus.CANCELLED,
                current.evidenceRefs(), current.result(), current.error());
        jobs.put(jobId, new StoredJob(organizationId, cancelled)); return cancelled;
    }

    private JobResponse once(String action, JobRequest request, Function<String, JobResponse> work) {
        require(request.organizationId(), "organizationId"); require(request.repositorySnapshotRef(), "repositorySnapshotRef");
        require(request.workspaceRef(), "workspaceRef"); require(request.idempotencyKey(), "idempotencyKey");
        return once(action, request.organizationId(), request.idempotencyKey(), EngineApi.idempotencyMaterial(request), work);
    }
    private JobResponse once(String action, String organizationId, String key, String material, Function<String, JobResponse> work) {
        String scope = organizationId + ":" + action + ":" + key;
        String fingerprint = hash(material);
        IdempotentResult prior = idempotency.get(scope);
        if (prior != null) {
            if (!prior.fingerprint().equals(fingerprint)) throw new EngineApi.IdempotencyConflictException(key);
            return prior.response();
        }
        String jobId = "suite-" + hash(scope).substring(0, 20);
        JobResponse response = work.apply(jobId);
        idempotency.put(scope, new IdempotentResult(fingerprint, response));
        return response;
    }
    private JobResponse failure(String organizationId, String jobId, ErrorCode code, String message, String externalStatus) {
        EngineError error = new EngineError(code, message, false, List.of(), null, null,
                "configure an approved suite adapter or supply independently reviewed business evidence");
        JobResponse response = new JobResponse("1.0", jobId, JobStatus.FAILED, List.of(), result(externalStatus), error);
        jobs.put(jobId, new StoredJob(organizationId, response)); return response;
    }
    private static Map<String, Object> result(String externalStatus) {
        return Map.of("externalStatus", externalStatus, "customerSuiteAccessed", false,
                "productionStateChanged", false, "evidenceFabricated", false,
                "financialDifferenceAccepted", false, "sodConflictAccepted", false,
                "workerModifiedGate", false);
    }
    private static boolean yes(Map<String, Object> policy, String key) { return Boolean.TRUE.equals(policy.get(key)); }
    private static boolean prohibited(Map<String, Object> policy) {
        return Set.of("modifyProductionConfiguration", "publishProductionTransport",
                "deployProductionSolution", "deploySalesforceProduction",
                "modifyUserPermission", "bulkDeleteBusinessData",
                "autoAcceptProcessDifference", "autoAcceptFinancialDifference",
                "autoAcceptSodConflict", "autoCutover", "autoDecommission",
                "controlPlaneExecution").stream().anyMatch(key -> yes(policy, key));
    }
    private static void require(String value, String name) { if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required"); }
    private static String hash(String value) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8))); }
        catch (NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
    }
}
