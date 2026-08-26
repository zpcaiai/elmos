package io.elmos.workflow;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;

/**
 * Provider-neutral contract for one durable task-workflow start intent.
 *
 * <p>The payload is deliberately typed and immutable.  It is suitable for a
 * transactional outbox adapter, but it does not import a workflow SDK or
 * claim that a workflow was started.  Tenant and account scope always comes
 * from the authenticated context; no payload field can replace it.</p>
 */
public final class TaskFinopsWorkflowStartPayload {
    public static final int PAYLOAD_VERSION = 1;
    public static final String SCHEMA_VERSION = "elmos.task-finops.workflow-start.v1";
    public static final String EXTERNAL_EVIDENCE = "NOT_RUN";
    public static final String PRODUCTION_CERTIFICATION = "NOT_CERTIFIED";

    public static final String ORGANIZATION_ID_ATTRIBUTE = "organization_id";
    public static final String ACCOUNT_ID_ATTRIBUTE = "account_id";
    public static final String ACTOR_ID_ATTRIBUTE = "actor_id";
    public static final String REQUEST_ID_ATTRIBUTE = "request_id";
    public static final String TASK_ID_ATTRIBUTE = "task_id";
    public static final String RUN_NUMBER_ATTRIBUTE = "run_number";
    public static final String WORKFLOW_ID_ATTRIBUTE = "workflow_id";
    public static final String WORKLOAD_CLASS_ATTRIBUTE = "workload_class";
    public static final String POLICY_VERSION_ATTRIBUTE = "policy_version";
    public static final String SCHEMA_VERSION_ATTRIBUTE = "schema_version";
    public static final String PAYLOAD_VERSION_ATTRIBUTE = "payload_version";
    public static final String PAYLOAD_DIGEST_ATTRIBUTE = "payload_digest";

    private static final String DIGEST_FORMAT = "ELMOS_MTF_WORKFLOW_START_PAYLOAD_V1";

    private final TaskFinopsPort.AuthenticatedContext context;
    private final TypedPayload payload;
    private final String payloadDigest;
    private final Map<String, String> searchAttributes;

    /**
     * The semantic task input carried to a workflow starter.  Identity is
     * intentionally not duplicated here; it is taken from {@link #context()}.
     */
    public record TypedPayload(
            String taskId,
            int runNumber,
            String workflowId,
            TaskFinopsPolicy.WorkloadClass workloadClass,
            int resourceUnits,
            String requestDigest,
            String inputManifestDigest,
            String policyVersion
    ) {
        public TypedPayload {
            taskId = identifier(taskId, "TASK", TaskFinopsPort.DATABASE_ID_MAX_LENGTH);
            if (runNumber < 1) {
                throw new IllegalArgumentException("ELMOS_MTF_WORKFLOW_RUN_INVALID");
            }
            workflowId = identifier(workflowId, "WORKFLOW_ID", 160);
            Objects.requireNonNull(workloadClass, "workloadClass");
            if (resourceUnits < 1 || resourceUnits > 64) {
                throw new IllegalArgumentException("ELMOS_MTF_WORKFLOW_RESOURCE_UNITS_INVALID");
            }
            int expectedUnits = TaskFinopsPolicy.workload(workloadClass).resourceUnits();
            if (resourceUnits != expectedUnits) {
                throw new IllegalArgumentException("ELMOS_MTF_WORKFLOW_RESOURCE_PROFILE_MISMATCH");
            }
            requestDigest = digest(requestDigest, "REQUEST");
            inputManifestDigest = optionalDigest(inputManifestDigest, "INPUT_MANIFEST");
            policyVersion = identifier(policyVersion, "POLICY_VERSION", 64);
        }
    }

    /**
     * A terminal local projection bound to this start intent.  The fixed
     * external statuses are intentional: local construction never certifies
     * an external provider or production execution.
     */
    public record TerminalProjection(
            TaskFinopsPort.AuthenticatedContext context,
            String taskId,
            int runNumber,
            String workflowId,
            TaskFinopsPolicy.TaskState taskState,
            TaskFinopsPolicy.Progress progress,
            Instant completedAt,
            String resultDigest,
            String payloadDigest,
            TaskFinopsAnalytics.ExternalEvidenceState externalEvidence,
            TaskFinopsAnalytics.ProviderOutcome providerOutcome,
            TaskFinopsAnalytics.ProductionCertification productionCertification
    ) {
        public TerminalProjection {
            Objects.requireNonNull(context, "context");
            taskId = identifier(taskId, "TASK", TaskFinopsPort.DATABASE_ID_MAX_LENGTH);
            if (runNumber < 1) {
                throw new IllegalArgumentException("ELMOS_MTF_WORKFLOW_RUN_INVALID");
            }
            workflowId = identifier(workflowId, "WORKFLOW_ID", 160);
            Objects.requireNonNull(taskState, "taskState");
            if (taskState != TaskFinopsPolicy.TaskState.SUCCEEDED
                    && taskState != TaskFinopsPolicy.TaskState.FAILED
                    && taskState != TaskFinopsPolicy.TaskState.CANCELLED) {
                throw new IllegalArgumentException("ELMOS_MTF_WORKFLOW_STATE_NOT_TERMINAL");
            }
            Objects.requireNonNull(progress, "progress");
            if ((taskState == TaskFinopsPolicy.TaskState.SUCCEEDED
                    && progress.percent() != 100)
                    || (taskState != TaskFinopsPolicy.TaskState.SUCCEEDED
                    && progress.percent() == 100)) {
                throw new IllegalArgumentException("ELMOS_MTF_WORKFLOW_TERMINAL_PROGRESS_INVALID");
            }
            Objects.requireNonNull(completedAt, "completedAt");
            resultDigest = optionalDigest(resultDigest, "RESULT");
            payloadDigest = digest(payloadDigest, "PAYLOAD");
            if (taskState == TaskFinopsPolicy.TaskState.SUCCEEDED
                    && resultDigest == null) {
                throw new IllegalArgumentException("ELMOS_MTF_WORKFLOW_RESULT_REQUIRED");
            }
            if (externalEvidence != TaskFinopsAnalytics.ExternalEvidenceState.NOT_RUN
                    || providerOutcome != TaskFinopsAnalytics.ProviderOutcome.UNKNOWN
                    || productionCertification
                    != TaskFinopsAnalytics.ProductionCertification.NOT_CERTIFIED) {
                throw new IllegalArgumentException("ELMOS_MTF_WORKFLOW_EXTERNAL_STATUS_INVALID");
            }
        }

        /** Digest of the terminal fields, for a local projection receipt. */
        public String projectionDigest() {
            MessageDigest digest = sha256();
            update(digest, "ELMOS_MTF_WORKFLOW_TERMINAL_PROJECTION_V1");
            update(digest, context.organizationId());
            update(digest, context.accountId());
            update(digest, context.actorId());
            update(digest, context.requestId());
            update(digest, taskId);
            update(digest, Integer.toString(runNumber));
            update(digest, workflowId);
            update(digest, taskState.name());
            update(digest, Short.toString(progress.percent()));
            update(digest, Long.toString(progress.elapsedMillis()));
            update(digest, Long.toString(progress.etaP50Millis()));
            update(digest, Long.toString(progress.etaP90Millis()));
            update(digest, completedAt.toString());
            update(digest, resultDigest);
            update(digest, payloadDigest);
            update(digest, externalEvidence.name());
            update(digest, providerOutcome.name());
            update(digest, productionCertification.name());
            return HexFormat.of().formatHex(digest.digest());
        }
    }

    public TaskFinopsWorkflowStartPayload(
            TaskFinopsPort.AuthenticatedContext context,
            TypedPayload payload
    ) {
        this.context = Objects.requireNonNull(context, "context");
        this.payload = Objects.requireNonNull(payload, "payload");
        this.payloadDigest = canonicalPayloadDigest(context, payload);
        this.searchAttributes = buildSearchAttributes(context, payload, payloadDigest);
    }

    /** Convenience constructor for the normal first-run task start. */
    public TaskFinopsWorkflowStartPayload(
            TaskFinopsPort.AuthenticatedContext context,
            String taskId,
            int runNumber,
            TaskFinopsPolicy.WorkloadClass workloadClass,
            String requestDigest,
            String inputManifestDigest,
            String policyVersion
    ) {
        this(context, new TypedPayload(
                taskId,
                runNumber,
                deterministicWorkflowId(taskId, runNumber),
                workloadClass,
                TaskFinopsPolicy.workload(workloadClass).resourceUnits(),
                requestDigest,
                inputManifestDigest,
                policyVersion));
    }

    /** Builds a payload using the repository's versioned workload policy. */
    public static TaskFinopsWorkflowStartPayload forTask(
            TaskFinopsPort.AuthenticatedContext context,
            String taskId,
            int runNumber,
            TaskFinopsPolicy.WorkloadClass workloadClass,
            String requestDigest
    ) {
        return new TaskFinopsWorkflowStartPayload(
                context, taskId, runNumber, workloadClass, requestDigest, null,
                WorkloadAwareScheduler.POLICY_VERSION);
    }

    /** Deterministic id shared by outbox replay and a future provider adapter. */
    public static String deterministicWorkflowId(String taskId, int runNumber) {
        String normalized = identifier(taskId, "TASK", TaskFinopsPort.DATABASE_ID_MAX_LENGTH);
        if (runNumber < 1) {
            throw new IllegalArgumentException("ELMOS_MTF_WORKFLOW_RUN_INVALID");
        }
        return runNumber == 1 ? "mtf-" + normalized : "mtf-" + normalized + "-r" + runNumber;
    }

    public TaskFinopsPort.AuthenticatedContext context() {
        return context;
    }

    public TypedPayload payload() {
        return payload;
    }

    public TypedPayload typedPayload() {
        return payload;
    }

    public int payloadVersion() {
        return PAYLOAD_VERSION;
    }

    public String schemaVersion() {
        return SCHEMA_VERSION;
    }

    /** Canonical SHA-256 over context, version and every semantic payload field. */
    public String payloadDigest() {
        return payloadDigest;
    }

    /** Immutable values suitable for a provider Search Attributes adapter. */
    public Map<String, String> searchAttributes() {
        return searchAttributes;
    }

    /** Builds a terminal projection without invoking a provider or workflow SDK. */
    public TerminalProjection terminalProjection(
            TaskFinopsPolicy.TaskState taskState,
            TaskFinopsPolicy.Progress progress,
            Instant completedAt,
            String resultDigest
    ) {
        return new TerminalProjection(
                context,
                payload.taskId(),
                payload.runNumber(),
                payload.workflowId(),
                taskState,
                progress,
                completedAt,
                resultDigest,
                payloadDigest,
                TaskFinopsAnalytics.ExternalEvidenceState.NOT_RUN,
                TaskFinopsAnalytics.ProviderOutcome.UNKNOWN,
                TaskFinopsAnalytics.ProductionCertification.NOT_CERTIFIED);
    }

    private static String canonicalPayloadDigest(
            TaskFinopsPort.AuthenticatedContext context,
            TypedPayload payload
    ) {
        MessageDigest digest = sha256();
        update(digest, DIGEST_FORMAT);
        update(digest, SCHEMA_VERSION);
        update(digest, Integer.toString(PAYLOAD_VERSION));
        update(digest, context.organizationId());
        update(digest, context.accountId());
        update(digest, context.actorId());
        // requestId is audit/trace metadata.  Excluding it makes a retry with
        // the same authenticated principal and immutable task input digest
        // to the same start intent.
        update(digest, payload.taskId());
        update(digest, Integer.toString(payload.runNumber()));
        update(digest, payload.workflowId());
        update(digest, payload.workloadClass().name());
        update(digest, Integer.toString(payload.resourceUnits()));
        update(digest, payload.requestDigest());
        update(digest, payload.inputManifestDigest());
        update(digest, payload.policyVersion());
        return HexFormat.of().formatHex(digest.digest());
    }

    private static Map<String, String> buildSearchAttributes(
            TaskFinopsPort.AuthenticatedContext context,
            TypedPayload payload,
            String payloadDigest
    ) {
        Map<String, String> attributes = new LinkedHashMap<>();
        attributes.put(ORGANIZATION_ID_ATTRIBUTE, context.organizationId());
        attributes.put(ACCOUNT_ID_ATTRIBUTE, context.accountId());
        attributes.put(ACTOR_ID_ATTRIBUTE, context.actorId());
        attributes.put(REQUEST_ID_ATTRIBUTE, context.requestId());
        attributes.put(TASK_ID_ATTRIBUTE, payload.taskId());
        attributes.put(RUN_NUMBER_ATTRIBUTE, Integer.toString(payload.runNumber()));
        attributes.put(WORKFLOW_ID_ATTRIBUTE, payload.workflowId());
        attributes.put(WORKLOAD_CLASS_ATTRIBUTE, payload.workloadClass().name());
        attributes.put(POLICY_VERSION_ATTRIBUTE, payload.policyVersion());
        attributes.put(SCHEMA_VERSION_ATTRIBUTE, SCHEMA_VERSION);
        attributes.put(PAYLOAD_VERSION_ATTRIBUTE, Integer.toString(PAYLOAD_VERSION));
        attributes.put(PAYLOAD_DIGEST_ATTRIBUTE, payloadDigest);
        return Map.copyOf(attributes);
    }

    private static String identifier(String value, String field, int maxLength) {
        String candidate = value == null ? "" : value.trim();
        if (candidate.isEmpty() || candidate.length() > maxLength
                || candidate.indexOf('\u0000') >= 0) {
            throw new IllegalArgumentException("ELMOS_MTF_" + field + "_INVALID");
        }
        return candidate;
    }

    private static String digest(String value, String field) {
        String candidate = value == null ? "" : value.trim().toLowerCase(Locale.ROOT);
        if (!candidate.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("ELMOS_MTF_" + field + "_DIGEST_INVALID");
        }
        return candidate;
    }

    private static String optionalDigest(String value, String field) {
        return value == null || value.isBlank() ? null : digest(value, field);
    }

    private static MessageDigest sha256() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("ELMOS_MTF_SHA256_UNAVAILABLE", exception);
        }
    }

    private static void update(MessageDigest digest, String value) {
        if (value == null) {
            digest.update(ByteBuffer.allocate(Integer.BYTES).putInt(-1).array());
            return;
        }
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        digest.update(ByteBuffer.allocate(Integer.BYTES).putInt(bytes.length).array());
        digest.update(bytes);
    }
}
