package io.elmos.databasedata;

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
public final class DatabaseDataEngineService {
    private record IdempotentResult(String fingerprint, JobResponse response) {}

    private final VendorRunnerRegistry runners;
    private final Map<String, JobResponse> jobs = new ConcurrentHashMap<>();
    private final Map<String, IdempotentResult> idempotency = new ConcurrentHashMap<>();

    public DatabaseDataEngineService() {
        this(new VendorRunnerRegistry());
    }

    DatabaseDataEngineService(VendorRunnerRegistry runners) {
        this.runners = Objects.requireNonNull(runners);
    }

    public Capabilities capabilities() {
        return new Capabilities(
                "1.0", "ELMOS_DATABASE_DATA", "1.0.0",
                List.of("SQL", "PLSQL", "TSQL", "PLPGSQL"),
                List.of("ORACLE_REGISTRY_BOUND", "SQL_SERVER_REGISTRY_BOUND",
                        "MYSQL_REGISTRY_BOUND", "POSTGRESQL_REGISTRY_BOUND"),
                List.of("TARGET_COMPATIBILITY_REGISTRY_BOUND"),
                List.of("VENDOR_CLI", "JDBC_NATIVE_DRIVER", "SPARK", "FLINK", "DBT"),
                List.of("OLTP_DATABASE", "ANALYTICS_PLATFORM", "BI_SEMANTIC"),
                List.of("SCHEMA_IR", "SQL_IR", "PROCEDURE_IR", "OPENLINEAGE"),
                runners.all().keySet().stream().map(Enum::name).sorted().toList(),
                List.of("ORACLE", "SQL_SERVER", "MYSQL", "POSTGRESQL",
                        "ICEBERG", "DELTA", "PARQUET", "BI"),
                List.of("SCHEMA_CONVERSION", "PROCEDURE_CONVERSION", "QUERY_REWRITE",
                        "BULK_LOAD", "CDC", "LAKEHOUSE", "SEMANTIC_MODEL"),
                List.of("DATA_RECONCILIATION", "QUERY_PERFORMANCE", "DATA_QUALITY",
                        "BI_METRIC", "BI_SECURITY", "LINEAGE", "GOVERNANCE", "CUTOVER"),
                Map.of(
                        "network", "DENY_BY_DEFAULT",
                        "credentials", "SHORT_LIVED_JOB_LEASE",
                        "discoveryPermissions", List.of("METADATA_READ", "CATALOG_READ",
                                "PLAN_READ", "PERFORMANCE_VIEW_READ"),
                        "productionWrites", "NAMED_APPROVAL_REQUIRED",
                        "customerCodeExecution", "RUNNER_REQUIRED_FAIL_CLOSED",
                        "runnerStatus", "NOT_CONFIGURED"));
    }

    public JobResponse scan(JobRequest request) {
        return once("scan", request, jobId -> failure(jobId, ErrorCode.DATABASE_RUNNER_REQUIRED,
                "approved read-only vendor Runner and short-lived credential lease are required; metadata was not captured"));
    }

    public JobResponse plan(JobRequest request) {
        return once("plan", request, jobId -> failure(jobId, ErrorCode.DATABASE_METADATA_INCOMPLETE,
                "immutable estate, workload, classification, ownership, and compatibility evidence are required"));
    }

    public JobResponse validate(JobRequest request) {
        return once("validate", request, jobId -> failure(jobId, ErrorCode.DATA_EVIDENCE_INCOMPLETE,
                "independent source and target result, performance, quality, BI, and governance evidence are required"));
    }

    public JobResponse executeStep(ExecuteStepRequest request) {
        require(request.organizationId(), "organizationId");
        require(request.migrationRunId(), "migrationRunId");
        require(request.workspaceRef(), "workspaceRef");
        require(request.idempotencyKey(), "idempotencyKey");
        return once("execute-step", request.organizationId(), request.idempotencyKey(), request.toString(),
                jobId -> failure(jobId,
                        request.stepDefinition().executorType() == ExecutorType.DATABASE_CDC
                                ? ErrorCode.DATABASE_CDC_PERMISSION_REQUIRED : ErrorCode.DATABASE_RUNNER_REQUIRED,
                        "approved capability-matched Runner and named production-operation approval are required"));
    }

    public JobResponse job(String organizationId, String jobId) {
        require(organizationId, "organizationId");
        require(jobId, "jobId");
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
        require(request.organizationId(), "organizationId");
        require(request.repositorySnapshotRef(), "repositorySnapshotRef");
        require(request.workspaceRef(), "workspaceRef");
        require(request.profile(), "profile");
        require(request.correlationId(), "correlationId");
        require(request.idempotencyKey(), "idempotencyKey");
        return once(operation, request.organizationId(), request.idempotencyKey(), request.toString(), action);
    }

    private JobResponse once(String operation, String organizationId, String key, String input,
                             Function<String, JobResponse> action) {
        String scopedKey = organizationId + ":" + operation + ":" + key;
        String currentFingerprint = hash(operation + "\n" + input);
        var previous = idempotency.get(scopedKey);
        if (previous != null) {
            if (!previous.fingerprint().equals(currentFingerprint)) {
                return failure(previous.response().jobId(), ErrorCode.POLICY_BLOCKED,
                        "idempotency key was reused with different input");
            }
            return previous.response();
        }
        String jobId = hash(scopedKey).substring(0, 24);
        JobResponse response = action.apply(jobId);
        idempotency.put(scopedKey, new IdempotentResult(currentFingerprint, response));
        jobs.put(organizationId + ":" + jobId, response);
        return response;
    }

    private JobResponse failure(String jobId, ErrorCode code, String message) {
        return new JobResponse("1.0", jobId, JobStatus.FAILED, List.of(),
                Map.of("configured", false, "executed", false, "customerCodeExecuted", false,
                        "evidenceFabricated", false, "externalStatus", "NOT_RUN"),
                new EngineError(code, message, false, List.of(), null, null,
                        "Configure and approve the required Runner, lease, provider, and independent evidence."));
    }

    private static String hash(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(impossible);
        }
    }

    private static void require(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required");
    }
}
