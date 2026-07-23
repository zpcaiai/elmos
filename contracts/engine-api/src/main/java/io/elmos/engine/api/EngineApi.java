package io.elmos.engine.api;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.PositiveOrZero;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;

public final class EngineApi {
    private EngineApi() {}

    public enum ExecutorType {
        SCANNER, OPENREWRITE, MSBUILD_EVALUATION, ROSLYN_TRANSFORMATION,
        PROJECT_SYSTEM_TRANSFORMATION, ASPNET_MIGRATION, WCF_MIGRATION, EF_MIGRATION,
        LIBCST, PYTHON_AST, UV, PIP, CONDA, MYPY, PYRIGHT, PYTEST,
        DATABASE_SCANNER, DATABASE_CONVERTER, DATABASE_QUERY_VALIDATOR,
        DATABASE_BULK_LOADER, DATABASE_CDC, DATA_QUALITY, DATA_PLATFORM, BI_VALIDATOR,
        INFRASTRUCTURE_SCANNER, VM_IMAGE_BUILDER, CONTAINER_BUILDER,
        KUBERNETES_VALIDATOR, SERVERLESS_VALIDATOR, IAC_PLANNER, IAC_APPLIER,
        NETWORK_VALIDATOR, OBSERVABILITY_VALIDATOR, FINOPS_VALIDATOR,
        RESILIENCE_VALIDATOR, MULTICLOUD_VALIDATOR, INFRASTRUCTURE_CUTOVER,
        SECURITY_ESTATE_DISCOVERY, IDENTITY_VALIDATOR, SECRET_SCANNER, CRYPTO_VALIDATOR,
        SAST, SCA, IAC_SECURITY_SCANNER, CONTAINER_SECURITY_SCANNER,
        DAST, API_SECURITY, RUNTIME_SECURITY, CLOUD_SECURITY, DLP,
        THREAT_MODELER, SBOM_GENERATOR, PROVENANCE_VERIFIER, VEX_VALIDATOR,
        CONTROL_ASSESSOR, OSCAL_VALIDATOR, SECURITY_AUTHORIZATION_REVIEW,
        UNIT_TEST, INTEGRATION_TEST, BROWSER_CLIENT_TEST, DATA_ML_TEST,
        PERFORMANCE_TEST, MUTATION_TEST,
        MAINFRAME_DISCOVERY, MAINFRAME_ANALYSIS, MAINFRAME_BUILD,
        MAINFRAME_TEST, MAINFRAME_PARALLEL_RUN, MAINFRAME_CUTOVER,
        INTEGRATION_DISCOVERY, INTEGRATION_ANALYSIS, BROKER_VALIDATION,
        API_GATEWAY_VALIDATION, B2B_VALIDATION, WORKFLOW_VALIDATION,
        INTEGRATION_REPLAY, INTEGRATION_CUTOVER,
        SUITE_DISCOVERY, SUITE_ANALYSIS, SAP_VALIDATION, ORACLE_VALIDATION,
        DYNAMICS_VALIDATION, SALESFORCE_VALIDATION, MASTER_DATA_VALIDATION,
        SUITE_DATA_MIGRATION, BUSINESS_PROCESS_VALIDATION,
        SUITE_INTEGRATION_VALIDATION, SUITE_CUTOVER,
        DELIVERY_DISCOVERY, SCM_MIGRATION, PIPELINE_VALIDATION, ARTIFACT_PROMOTION,
        ENVIRONMENT_LIFECYCLE, PLATFORM_ACCEPTANCE, SELF_SERVICE_OPERATION,
        AI_DISCOVERY, CPU_TRAINING, GPU_TRAINING, AI_EVALUATION, RAG_VALIDATION,
        AGENT_SANDBOX, AI_DEPLOYMENT, AI_MONITORING,
        OT_DISCOVERY, PROTOCOL_VALIDATION, EDGE_RUNTIME_VALIDATION, OTA_VALIDATION,
        EDGE_AI_VALIDATION, SIL_VALIDATION, HIL_VALIDATION, OT_COMMAND, OT_CUTOVER,
        OPERATIONS_DISCOVERY, EVENT_CORRELATION, INCIDENT_SIMULATION,
        RUNBOOK_AUTOMATION, CAPACITY_SIMULATION, CONTINUITY_DRILL,
        OPERATIONS_REMEDIATION, OPERATIONS_CHANGE,
        EA_DISCOVERY, EA_ASSESSMENT, EA_OPTION_EVALUATION, EA_ROADMAP_SIMULATION,
        EA_DECISION, EA_CONFORMANCE,
        DATA_VALIDATOR, MODEL_VALIDATOR, BUILD_TOOL, TEST_RUNNER, CODING_AGENT,
        SONARQUBE, CONTRACT_CHECKER, HUMAN_REVIEW, UNKNOWN
    }
    public enum JobStatus { ACCEPTED, RUNNING, SUCCEEDED, FAILED, CANCELLED }
    public enum ErrorCode {
        REPOSITORY_UNAVAILABLE, WORKSPACE_UNAVAILABLE, BUILD_TOOL_NOT_FOUND,
        DEPENDENCY_RESOLUTION_FAILED, BASELINE_COMPILE_FAILED, BASELINE_TEST_FAILED,
        RECIPE_NOT_ALLOWED, RECIPE_EXECUTION_FAILED, AGENT_BUDGET_EXCEEDED,
        VALIDATION_FAILED, POLICY_BLOCKED, HUMAN_REVIEW_REQUIRED,
        DOTNET_SOLUTION_NOT_FOUND, DOTNET_MULTIPLE_SOLUTION_AMBIGUOUS, MSBUILD_NOT_AVAILABLE,
        MSBUILD_VERSION_INCOMPATIBLE, MSBUILD_EVALUATION_FAILED,
        VISUAL_STUDIO_COMPONENT_MISSING, TARGETING_PACK_MISSING, NUGET_RESTORE_FAILED,
        ROSLYN_LOAD_FAILED, PROJECT_TYPE_UNSUPPORTED, WINDOWS_RUNNER_REQUIRED,
        MODERN_DOTNET_RUNNER_REQUIRED, PYTHON_PROJECT_NOT_FOUND,
        PYTHON_MULTIPLE_PROJECT_ROOTS, PYTHON_INTERPRETER_UNAVAILABLE,
        PYTHON_VERSION_UNRESOLVED, PYTHON_ENVIRONMENT_UNREPRODUCIBLE,
        PYTHON_DEPENDENCY_RESOLUTION_FAILED, PYTHON_WHEEL_UNAVAILABLE,
        PYTHON_NATIVE_LIBRARY_MISSING, PYTHON_CST_PARSE_FAILED,
        PYTHON_TYPE_ANALYSIS_INCOMPLETE, PYTHON_RUNTIME_TRACE_FAILED,
        GPU_RUNNER_REQUIRED, LEGACY_PYTHON_RUNNER_REQUIRED, NOTEBOOK_STATE_UNRESOLVED,
        DATABASE_CONNECTION_FAILED, DATABASE_VERSION_UNSUPPORTED,
        DATABASE_PERMISSION_INSUFFICIENT, DATABASE_METADATA_INCOMPLETE,
        DATABASE_WORKLOAD_CAPTURE_FAILED, DATABASE_TARGET_UNAVAILABLE,
        DATABASE_CDC_PERMISSION_REQUIRED, DATA_PLATFORM_ENGINE_UNAVAILABLE,
        DATABASE_RUNNER_REQUIRED, DATA_EVIDENCE_INCOMPLETE,
        INFRASTRUCTURE_PROVIDER_UNAVAILABLE, INFRASTRUCTURE_CREDENTIAL_INSUFFICIENT,
        INFRASTRUCTURE_DISCOVERY_INCOMPLETE, INFRASTRUCTURE_RATE_LIMITED,
        INFRASTRUCTURE_REGION_NOT_ALLOWED, INFRASTRUCTURE_TARGET_CAPABILITY_MISSING,
        INFRASTRUCTURE_CHANGE_POLICY_BLOCKED, INFRASTRUCTURE_PLAN_REQUIRED,
        INFRASTRUCTURE_APPROVAL_REQUIRED, INFRASTRUCTURE_RUNNER_REQUIRED,
        INFRASTRUCTURE_EVIDENCE_INCOMPLETE, INTERNAL_ENGINE_ERROR, UNKNOWN,
        SECURITY_SCOPE_UNRESOLVED, SECURITY_TOOL_UNAVAILABLE, SECURITY_TOOL_LICENSE_BLOCKED,
        SECURITY_SCAN_INCOMPLETE, SECURITY_TEST_AUTHORIZATION_REQUIRED,
        SECURITY_TARGET_UNREACHABLE, SECURITY_EVIDENCE_INVALID,
        SECURITY_CONTROL_CATALOG_MISSING,
        TEST_QUALITY_RUNNER_REQUIRED, TEST_DISCOVERY_INCOMPLETE,
        TEST_ENVIRONMENT_UNAVAILABLE, TEST_DATA_INVALID,
        TEST_EVIDENCE_STALE, TEST_QUALITY_GATE_FAILED,
        AI_TEST_REVIEW_REQUIRED,
        MAINFRAME_RUNNER_REQUIRED, MAINFRAME_LEASE_REQUIRED,
        MAINFRAME_ESTATE_INCOMPLETE, COPYBOOK_VERSION_AMBIGUOUS,
        RUNTIME_SOURCE_MISMATCH, JCL_FLOW_INCOMPLETE,
        MAINFRAME_SEMANTIC_DIFFERENCE, PARALLEL_RUN_DIFFERENCE,
        MAINFRAME_PRODUCTION_APPROVAL_REQUIRED, MAINFRAME_CUTOVER_BLOCKED,
        MAINFRAME_DECOMMISSION_BLOCKED,
        INTEGRATION_PLATFORM_UNAVAILABLE, INTEGRATION_PERMISSION_INSUFFICIENT,
        INTEGRATION_CONFIG_EXPORT_FAILED, INTEGRATION_RUNTIME_METADATA_FAILED,
        BROKER_TEST_ENVIRONMENT_FAILED, PARTNER_TEST_AUTHORIZATION_REQUIRED,
        MESSAGE_REPLAY_NOT_AUTHORIZED, INTEGRATION_RUNNER_REQUIRED,
        INTEGRATION_LEASE_REQUIRED, INTEGRATION_ESTATE_INCOMPLETE,
        DELIVERY_SEMANTICS_UNKNOWN, UNKNOWN_PRODUCER, UNKNOWN_CONSUMER,
        UNKNOWN_PARTNER, SCHEMA_AMBIGUOUS, MESSAGE_ORDERING_RISK,
        INTEGRATION_PRODUCTION_APPROVAL_REQUIRED, INTEGRATION_CUTOVER_BLOCKED,
        INTEGRATION_DECOMMISSION_BLOCKED,
        SUITE_PLATFORM_UNAVAILABLE, SUITE_PERMISSION_INSUFFICIENT,
        SUITE_METADATA_EXPORT_FAILED, SUITE_RUNNER_REQUIRED,
        SUITE_LEASE_REQUIRED, SUITE_ESTATE_INCOMPLETE,
        BUSINESS_PROCESS_UNKNOWN, CUSTOMIZATION_OWNER_UNKNOWN,
        CLEAN_CORE_VIOLATION, MASTER_DATA_UNRESOLVED,
        TARGET_STANDARD_GAP, EXTENSION_INCOMPATIBLE,
        ROLE_MAPPING_FAILED, SOD_CONFLICT,
        DATA_RECONCILIATION_FAILED, FINANCIAL_BALANCE_FAILED,
        INVENTORY_RECONCILIATION_FAILED, PROCESS_EQUIVALENCE_FAILED,
        SUITE_SANDBOX_AUTHORIZATION_REQUIRED,
        SUITE_DATA_MIGRATION_AUTHORIZATION_REQUIRED,
        SUITE_PRODUCTION_APPROVAL_REQUIRED, SUITE_CUTOVER_BLOCKED,
        SUITE_DECOMMISSION_BLOCKED,
        PLATFORM_RUNNER_REQUIRED, PLATFORM_LEASE_REQUIRED, PLATFORM_ESTATE_INCOMPLETE,
        SELF_SERVICE_AUTHORIZATION_REQUIRED, PLATFORM_PRODUCTION_APPROVAL_REQUIRED,
        AI_RUNNER_REQUIRED, AI_DATA_LEASE_REQUIRED, AI_ESTATE_INCOMPLETE,
        AI_TRAINING_AUTHORIZATION_REQUIRED, AI_DEPLOYMENT_APPROVAL_REQUIRED,
        AGENT_TOOL_APPROVAL_REQUIRED,
        OT_SITE_RUNNER_REQUIRED, OT_LEASE_REQUIRED, OT_ESTATE_INCOMPLETE,
        OT_COMMAND_APPROVAL_REQUIRED, OT_SAFETY_OPERATION_PROHIBITED,
        OT_PRODUCTION_APPROVAL_REQUIRED,
        OPERATIONS_RUNNER_REQUIRED, OPERATIONS_LEASE_REQUIRED,
        OPERATIONS_ESTATE_INCOMPLETE, REMEDIATION_APPROVAL_REQUIRED,
        HIGH_RISK_CHANGE_APPROVAL_REQUIRED,
        EA_RUNNER_REQUIRED, EA_LEASE_REQUIRED, EA_ESTATE_INCOMPLETE,
        ARCHITECTURE_DECISION_APPROVAL_REQUIRED, INVESTMENT_APPROVAL_REQUIRED,
        ARCHITECTURE_EXCEPTION_APPROVAL_REQUIRED
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Capabilities(String schemaVersion, @JsonAlias("engine") String engineName, String engineVersion, List<String> languages,
                               @JsonAlias("sourceVersions") List<String> supportedSourceVersions, List<String> supportedTargetVersions,
                               List<String> buildSystems, List<String> solutionFormats, @JsonAlias("projectModels") List<String> projectFormats,
                               List<String> runnerProfiles, @JsonAlias("frameworks") List<String> supportedFrameworks, List<String> availableRecipes,
                               List<String> validationCapabilities, Map<String,Object> sandboxRequirements) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record JobRequest(@NotBlank String organizationId, @NotBlank String repositorySnapshotRef,
                             @NotBlank String workspaceRef, @NotBlank String profile,
                             @NotBlank String correlationId, @NotBlank String idempotencyKey,
                             @NotNull Map<String,Object> options) {
        public JobRequest {
            requireText(organizationId, "organizationId");
            requireText(repositorySnapshotRef, "repositorySnapshotRef");
            requireText(workspaceRef, "workspaceRef");
            requireText(profile, "profile");
            requireText(correlationId, "correlationId");
            requireText(idempotencyKey, "idempotencyKey");
            options = canonicalMap(options);
        }

        public JobRequest(String organizationId, String repositorySnapshotRef, String workspaceRef, String profile,
                          String correlationId, String idempotencyKey) {
            this(organizationId, repositorySnapshotRef, workspaceRef, profile, correlationId, idempotencyKey, Map.of());
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record ExecuteStepRequest(@NotBlank String organizationId, @NotBlank String migrationRunId,
                                     @Positive int migrationPlanVersion,
                                     @NotNull @Valid StepDefinition stepDefinition, @NotBlank String workspaceRef,
                                     @NotBlank String sourceCommit, @NotNull @Valid ExecutionBudget executionBudget,
                                     Map<String,Object> policy, @NotBlank String correlationId,
                                     @NotBlank String idempotencyKey) {
        public ExecuteStepRequest {
            requireText(organizationId, "organizationId");
            requireText(migrationRunId, "migrationRunId");
            if (migrationPlanVersion <= 0) throw new IllegalArgumentException("migrationPlanVersion must be positive");
            Objects.requireNonNull(stepDefinition, "stepDefinition is required");
            requireText(workspaceRef, "workspaceRef");
            requireText(sourceCommit, "sourceCommit");
            Objects.requireNonNull(executionBudget, "executionBudget is required");
            policy = canonicalMap(policy);
            requireText(correlationId, "correlationId");
            requireText(idempotencyKey, "idempotencyKey");
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record StepDefinition(@NotBlank String stepId, @NotNull ExecutorType executorType,
                                 @NotNull Map<String,Object> configuration) {
        public StepDefinition {
            requireText(stepId, "stepId");
            Objects.requireNonNull(executorType, "executorType is required");
            configuration = canonicalMap(configuration);
        }
    }
    public record ExecutionBudget(@Positive long timeoutSeconds, @Positive long cpuSeconds,
                                  @PositiveOrZero long maxBytesWritten, @PositiveOrZero long maxAgentCredits) {
        public ExecutionBudget {
            if (timeoutSeconds <= 0) throw new IllegalArgumentException("timeoutSeconds must be positive");
            if (cpuSeconds <= 0) throw new IllegalArgumentException("cpuSeconds must be positive");
            if (maxBytesWritten < 0) throw new IllegalArgumentException("maxBytesWritten must be non-negative");
            if (maxAgentCredits < 0) throw new IllegalArgumentException("maxAgentCredits must be non-negative");
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record JobResponse(String schemaVersion, String jobId, JobStatus status, List<String> evidenceRefs,
                              Map<String,Object> result, EngineError error) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record EngineError(ErrorCode errorCode, String message, boolean retryable, List<String> evidenceRefs,
                              String failedCommand, String sanitizedLogRef, String suggestedAction) {}

    public static boolean isTerminal(JobStatus status) {
        return status == JobStatus.SUCCEEDED || status == JobStatus.FAILED || status == JobStatus.CANCELLED;
    }

    public static String idempotencyMaterial(Object request) {
        if (request instanceof JobRequest job) {
            return lengthPrefixed(job.repositorySnapshotRef(), job.workspaceRef(), job.profile(), job.options());
        }
        if (request instanceof ExecuteStepRequest execute) {
            return lengthPrefixed(execute.migrationRunId(), execute.migrationPlanVersion(),
                    execute.stepDefinition().stepId(), execute.stepDefinition().executorType().name(),
                    execute.stepDefinition().configuration(), execute.workspaceRef(), execute.sourceCommit(),
                    execute.executionBudget().timeoutSeconds(), execute.executionBudget().cpuSeconds(),
                    execute.executionBudget().maxBytesWritten(), execute.executionBudget().maxAgentCredits(),
                    execute.policy());
        }
        return lengthPrefixed(request);
    }

    public static final class JobNotFoundException extends RuntimeException {
        public JobNotFoundException(String jobId) { super("job not found: " + jobId); }
    }

    public static final class JobConflictException extends RuntimeException {
        public JobConflictException(String jobId) { super("job is already terminal: " + jobId); }
    }

    public static final class IdempotencyConflictException extends RuntimeException {
        public IdempotencyConflictException(String key) { super("idempotency key was already used: " + key); }
    }

    private static void requireText(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required");
    }

    private static Map<String, Object> canonicalMap(Map<String, Object> value) {
        if (value == null || value.isEmpty()) return Map.of();
        var sorted = new TreeMap<String, Object>();
        value.forEach((key, item) -> {
            if (key == null) throw new IllegalArgumentException("map keys must be strings");
            sorted.put(key, canonicalValue(item));
        });
        return Collections.unmodifiableMap(sorted);
    }

    private static Object canonicalValue(Object value) {
        if (value instanceof Map<?, ?> map) {
            var sorted = new TreeMap<String, Object>();
            map.forEach((key, item) -> {
                if (!(key instanceof String text)) throw new IllegalArgumentException("nested map keys must be strings");
                sorted.put(text, canonicalValue(item));
            });
            return Collections.unmodifiableMap(sorted);
        }
        if (value instanceof List<?> list) {
            var canonical = new ArrayList<>(list.size());
            list.forEach(item -> canonical.add(canonicalValue(item)));
            return Collections.unmodifiableList(canonical);
        }
        return value;
    }

    private static String lengthPrefixed(Object... values) {
        var material = new StringBuilder();
        for (Object value : values) {
            String text = canonicalText(value);
            material.append(text.length()).append(':').append(text);
        }
        return material.toString();
    }

    private static String canonicalText(Object value) {
        if (value == null) return "N";
        if (value instanceof String text) return "S" + text;
        if (value instanceof Boolean flag) return flag ? "B1" : "B0";
        if (value instanceof Number number) {
            try {
                return "D" + new BigDecimal(number.toString()).stripTrailingZeros().toPlainString();
            } catch (NumberFormatException invalidJsonNumber) {
                throw new IllegalArgumentException("numeric request values must be finite JSON numbers", invalidJsonNumber);
            }
        }
        if (value instanceof Enum<?> enumeration) return "E" + enumeration.name();
        if (value instanceof Map<?, ?> map) {
            var entries = new TreeMap<String, Object>();
            map.forEach((key, item) -> {
                if (!(key instanceof String text)) throw new IllegalArgumentException("request map keys must be strings");
                entries.put(text, item);
            });
            var content = new StringBuilder("M");
            entries.forEach((key, item) -> content.append(lengthPrefixed(key, item)));
            return content.toString();
        }
        if (value instanceof List<?> list) {
            var content = new StringBuilder("L");
            list.forEach(item -> content.append(lengthPrefixed(item)));
            return content.toString();
        }
        return "O" + value.getClass().getName() + ":" + value;
    }
}
