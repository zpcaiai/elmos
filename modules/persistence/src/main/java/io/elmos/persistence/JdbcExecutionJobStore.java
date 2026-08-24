package io.elmos.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.workflow.ExecutionJobPort;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.support.TransactionTemplate;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Base64;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import java.util.function.Supplier;

/**
 * PostgreSQL 17 adapter for {@link ExecutionJobPort}.
 *
 * <p>Every state transition delegates to the repository-owned Flyway V73
 * compatibility wrappers. That is
 * deliberate: the claim is a {@code FOR UPDATE ... SKIP LOCKED} loop with
 * per-tenant fairness, and expressing it in Java would either need a table lock
 * or would race two schedulers against each other.</p>
 *
 * <p>Style follows {@code JdbcSelfServiceBillingStore}: {@link JdbcClient} plus an
 * explicit {@link TransactionTemplate}, RLS bound inside the same transaction as
 * the work.</p>
 */
public final class JdbcExecutionJobStore implements ExecutionJobPort {

    private static final SecureRandom RANDOM = new SecureRandom();
    private static final int LEASE_TOKEN_BYTES = 32;

    private final JdbcClient jdbc;
    private final TransactionTemplate transactions;
    private final ObjectMapper json;

    public JdbcExecutionJobStore(JdbcClient jdbc, TransactionTemplate transactions, ObjectMapper json) {
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
        this.transactions = Objects.requireNonNull(transactions, "transactions");
        this.json = Objects.requireNonNull(json, "json");
    }

    // ---- tenant facing -----------------------------------------------------

    @Override
    public String enqueue(EnqueueCommand command) {
        requireIdentifier(command.organizationId(), "organizationId");
        requireIdentifier(command.accountId(), "accountId");
        requireIdentifier(command.jobId(), "jobId");
        requireValue(command.actorId(), 128, "ACTOR_ID");
        requireValue(command.requestId(), 160, "REQUEST_ID");
        requireWorkload(command.workloadClass(), command.resourceUnits());
        return inTaskContext(command, () -> mapDomainErrors(() ->
                jdbc.sql("""
                        SELECT elmos_mtf_enqueue_execution_job(
                            :jobId, :organizationId, :accountId, :actorId,
                            :businessLine, :jobKind,
                            :idempotencyKey, :requestDigest, cast(:payload AS jsonb),
                            :capability, :image, :priority, :budget, :maxAttempts,
                            :requestId, :workloadClass, :resourceUnits)
                        """)
                        .param("jobId", command.jobId())
                        .param("organizationId", command.organizationId())
                        .param("accountId", command.accountId())
                        .param("actorId", command.actorId())
                        .param("businessLine", command.businessLine().name())
                        .param("jobKind", command.jobKind())
                        .param("idempotencyKey", command.idempotencyKey())
                        .param("requestDigest", command.requestDigest())
                        .param("payload", writeJson(command.requestPayload()))
                        .param("capability", command.requiredCapability())
                        .param("image", command.runnerImage())
                        .param("priority", command.priority())
                        .param("budget", command.budgetWallSeconds())
                        .param("maxAttempts", command.maxAttempts())
                        .param("requestId", command.requestId())
                        .param("workloadClass", command.workloadClass())
                        .param("resourceUnits", command.resourceUnits())
                        .query(String.class).single()));
    }

    @Override
    public Optional<JobView> find(AuthenticatedContext context, String jobId) {
        requireContext(context);
        requireIdentifier(jobId, "jobId");
        return inIdentityContext(context, () ->
                jdbc.sql("""
                        SELECT job.*,
                               elmos_mtf_queue_position(job.job_id) AS queue_position
                          FROM execution_jobs job
                         WHERE job.organization_id = :organizationId
                           AND job.account_id = :accountId
                           AND job.job_id = :jobId
                        """)
                        .param("organizationId", context.organizationId())
                        .param("accountId", context.accountId())
                        .param("jobId", jobId)
                        .query(this::readJob)
                        .optional());
    }

    @Override
    public List<JobView> list(
            AuthenticatedContext context,
            BusinessLine businessLine,
            int limit,
            int offset
    ) {
        requireContext(context);
        int boundedLimit = Math.min(Math.max(limit, 1), 100);
        return inIdentityContext(context, () ->
                jdbc.sql("""
                        SELECT job.*,
                               elmos_mtf_queue_position(job.job_id) AS queue_position
                          FROM execution_jobs job
                         WHERE job.organization_id = :organizationId
                           AND job.account_id = :accountId
                           AND (cast(:businessLine AS varchar) IS NULL
                                OR job.business_line = cast(:businessLine AS varchar))
                         ORDER BY job.created_at DESC
                         LIMIT :limit OFFSET :offset
                        """)
                        .param("organizationId", context.organizationId())
                        .param("accountId", context.accountId())
                        .param("businessLine", businessLine == null ? null : businessLine.name())
                        .param("limit", boundedLimit)
                        .param("offset", Math.max(offset, 0))
                        .query(this::readJob)
                        .list());
    }

    @Override
    public Status requestCancel(AuthenticatedContext context, String jobId) {
        requireContext(context);
        requireIdentifier(jobId, "jobId");
        return inIdentityContext(context, () -> {
            jdbc.sql("""
                    SELECT job.job_id
                      FROM execution_jobs job
                     WHERE job.organization_id = :organizationId
                       AND job.account_id = :accountId
                       AND job.job_id = :jobId
                     FOR UPDATE
                    """)
                    .param("organizationId", context.organizationId())
                    .param("accountId", context.accountId())
                    .param("jobId", jobId)
                    .query(String.class)
                    .optional()
                    .orElseThrow(() -> new ExecutionStateException(
                            "ELMOS_EXECUTION_JOB_UNKNOWN"));
            return Status.valueOf(
                    jdbc.sql("""
                            SELECT elmos_mtf_request_execution_cancel(
                                :organizationId, :accountId, :jobId, :actorId)
                            """)
                        .param("organizationId", context.organizationId())
                        .param("accountId", context.accountId())
                        .param("jobId", jobId)
                        .param("actorId", context.actorId())
                        .query(String.class).single());
        });
    }

    // ---- runner facing -----------------------------------------------------

    @Override
    public List<LeaseGrant> claim(String runnerNodeId, List<String> capabilities, int limit, int leaseSeconds) {
        int bounded = Math.min(Math.max(limit, 1), 16);

        // One credential per potential slot. Unused ones are simply discarded:
        // generating them up front keeps the claim a single round trip while the
        // plaintext still never touches the database.
        List<String> leaseIds = new ArrayList<>(bounded);
        List<String> tokens = new ArrayList<>(bounded);
        List<String> hashes = new ArrayList<>(bounded);
        for (int i = 0; i < bounded; i++) {
            String token = randomToken();
            leaseIds.add("lease-" + UUID.randomUUID());
            tokens.add(token);
            hashes.add(sha256Hex(token));
        }

        return transactions.execute(status -> mapDomainErrors(() -> {
            List<LeaseGrant> grants = jdbc.sql("""
                    SELECT * FROM elmos_mtf_claim_execution_jobs(
                        :runnerNodeId, cast(:capabilities AS text[]), :limit, :leaseSeconds,
                        cast(:leaseIds AS text[]), cast(:tokenHashes AS text[]))
                    """)
                    .param("runnerNodeId", runnerNodeId)
                    .param("capabilities", toPgArray(capabilities))
                    .param("limit", bounded)
                    .param("leaseSeconds", leaseSeconds)
                    .param("leaseIds", toPgArray(leaseIds))
                    .param("tokenHashes", toPgArray(hashes))
                    .query((ResultSet rs, int row) -> new LeaseGrant(
                            rs.getString("job_id"),
                            rs.getString("organization_id"),
                            rs.getString("lease_id"),
                            "",
                            rs.getObject("lease_expires_at", java.time.OffsetDateTime.class).toInstant(),
                            BusinessLine.valueOf(rs.getString("business_line")),
                            rs.getString("job_kind"),
                            rs.getString("runner_image"),
                            rs.getInt("budget_wall_seconds"),
                            rs.getInt("budget_cpu_millis"),
                            rs.getInt("budget_memory_mib"),
                            rs.getShort("attempt"),
                            readJson(rs.getString("checkpoint_cursor")),
                            readJson(rs.getString("request_payload"))))
                    .list();

            // Re-attach the plaintext credential to the leases that were actually
            // granted, matching on lease id rather than on position.
            List<LeaseGrant> withTokens = new ArrayList<>(grants.size());
            for (LeaseGrant grant : grants) {
                int index = leaseIds.indexOf(grant.leaseId());
                withTokens.add(new LeaseGrant(
                        grant.jobId(), grant.organizationId(), grant.leaseId(), tokens.get(index),
                        grant.leaseExpiresAt(), grant.businessLine(), grant.jobKind(), grant.runnerImage(),
                        grant.budgetWallSeconds(), grant.budgetCpuMillis(), grant.budgetMemoryMib(),
                        grant.attempt(), grant.checkpointCursor(), grant.requestPayload()));
            }
            return withTokens;
        }));
    }

    @Override
    public HeartbeatResult heartbeat(HeartbeatCommand command) {
        return transactions.execute(status -> mapDomainErrors(() ->
                jdbc.sql("""
                        SELECT * FROM elmos_mtf_heartbeat_execution_lease(
                            :leaseId, :runnerNodeId, :tokenHash, :stage, :progress,
                            cast(:checkpoint AS jsonb), :leaseSeconds)
                        """)
                        .param("leaseId", command.leaseId())
                        .param("runnerNodeId", command.runnerNodeId())
                        .param("tokenHash", sha256Hex(command.leaseToken()))
                        .param("stage", command.stage())
                        .param("progress", command.progress())
                        .param("checkpoint", command.checkpoint() == null ? null : writeJson(command.checkpoint()))
                        .param("leaseSeconds", command.leaseSeconds())
                        .query((ResultSet rs, int row) -> new HeartbeatResult(
                                rs.getBoolean("cancel_requested"),
                                rs.getBoolean("pause_requested"),
                                rs.getObject("lease_expires_at", java.time.OffsetDateTime.class).toInstant()))
                        .single()));
    }

    @Override
    public boolean complete(CompletionCommand command) {
        return transactions.execute(status -> mapDomainErrors(() ->
                jdbc.sql("""
                        SELECT elmos_mtf_complete_execution_job(
                            :leaseId, :runnerNodeId, :tokenHash, :status, :resultStatus, :failureCode)
                        """)
                        .param("leaseId", command.leaseId())
                        .param("runnerNodeId", command.runnerNodeId())
                        .param("tokenHash", sha256Hex(command.leaseToken()))
                        .param("status", command.status().name())
                        .param("resultStatus", command.resultStatus() == null ? null : command.resultStatus().name())
                        .param("failureCode", command.failureCode())
                        .query(Boolean.class).single()));
    }

    @Override
    public int reapExpiredLeases() {
        return transactions.execute(status ->
                jdbc.sql("SELECT elmos_mtf_reap_execution_leases()").query(Integer.class).single());
    }

    // ---- infrastructure ----------------------------------------------------

    private <T> T inIdentityContext(AuthenticatedContext context, Supplier<T> work) {
        return transactions.execute(status -> mapDomainErrors(() -> {
            jdbc.sql("""
                    SELECT elmos_mtf_bind_identity(
                        cast(:organizationId AS varchar), cast(:accountId AS varchar),
                        cast(:actorId AS varchar), cast(:requestId AS varchar))
                    """)
                    .param("organizationId", context.organizationId())
                    .param("accountId", context.accountId())
                    .param("actorId", context.actorId())
                    .param("requestId", context.requestId())
                    .query()
                    .singleRow();
            return work.get();
        }));
    }

    private <T> T inTaskContext(EnqueueCommand command, Supplier<T> work) {
        return transactions.execute(status -> {
            setLocal("app.organization_id", command.organizationId());
            setLocal("app.account_id", command.accountId());
            setLocal("app.actor_id", command.actorId());
            setLocal("app.request_id", command.requestId());
            setLocal("app.workload_class", command.workloadClass());
            return work.get();
        });
    }

    private void setLocal(String setting, String value) {
        jdbc.sql("SELECT set_config(:setting, :value, true)")
                .param("setting", setting)
                .param("value", value)
                .query(String.class)
                .single();
    }

    private JobView readJob(ResultSet rs, int rowNum) throws SQLException {
        return new JobView(
                rs.getString("job_id"),
                rs.getString("organization_id"),
                rs.getString("account_id"),
                rs.getString("actor_id"),
                BusinessLine.valueOf(rs.getString("business_line")),
                rs.getString("job_kind"),
                Status.valueOf(rs.getString("status")),
                rs.getString("admission_state"),
                rs.getObject("queue_position", Integer.class),
                rs.getString("stage"),
                rs.getShort("progress"),
                ResultStatus.valueOf(rs.getString("result_status")),
                rs.getString("failure_code"),
                rs.getShort("attempt"),
                rs.getShort("max_attempts"),
                instant(rs, "created_at"),
                instant(rs, "started_at"),
                instant(rs, "finished_at"),
                rs.getObject("cancel_requested_at") != null,
                rs.getLong("state_version"));
    }

    private static Instant instant(ResultSet rs, String column) throws SQLException {
        java.time.OffsetDateTime value = rs.getObject(column, java.time.OffsetDateTime.class);
        return value == null ? null : value.toInstant();
    }

    /**
     * Translates the {@code ELMOS_*} exceptions raised by the V73 wrappers into a
     * typed domain failure. The raw PostgreSQL message never leaves this method, so
     * a public API response cannot leak schema or query text.
     */
    private static <T> T mapDomainErrors(Supplier<T> work) {
        try {
            return work.get();
        } catch (RuntimeException ex) {
            String message = rootMessage(ex);
            int marker = message == null ? -1 : message.indexOf("ELMOS_");
            if (marker >= 0) {
                String tail = message.substring(marker);
                int end = 0;
                while (end < tail.length()) {
                    char character = tail.charAt(end);
                    if (!(character == '_'
                            || character >= 'A' && character <= 'Z'
                            || character >= '0' && character <= '9')) {
                        break;
                    }
                    end++;
                }
                throw new ExecutionStateException(
                        end > 0 ? tail.substring(0, end) : "ELMOS_EXECUTION_STATE_INVALID");
            }
            throw ex;
        }
    }

    private static String rootMessage(Throwable throwable) {
        Throwable current = throwable;
        while (current.getCause() != null && current.getCause() != current) {
            current = current.getCause();
        }
        return current.getMessage();
    }

    private String writeJson(Map<String, Object> value) {
        try {
            return json.writeValueAsString(value == null ? Map.of() : value);
        } catch (Exception ex) {
            throw new ExecutionStateException("ELMOS_EXECUTION_PAYLOAD_UNSERIALIZABLE");
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> readJson(String value) {
        if (value == null || value.isBlank()) {
            return Map.of();
        }
        try {
            return json.readValue(value, Map.class);
        } catch (Exception ex) {
            throw new ExecutionStateException("ELMOS_EXECUTION_PAYLOAD_UNREADABLE");
        }
    }

    private static String toPgArray(List<String> values) {
        StringBuilder builder = new StringBuilder("{");
        for (int i = 0; i < values.size(); i++) {
            if (i > 0) {
                builder.append(',');
            }
            builder.append('"').append(values.get(i).replace("\"", "\\\"")).append('"');
        }
        return builder.append('}').toString();
    }

    private static String randomToken() {
        byte[] bytes = new byte[LEASE_TOKEN_BYTES];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    private static String sha256Hex(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest(value.getBytes(StandardCharsets.UTF_8)))
                    .toLowerCase(Locale.ROOT);
        } catch (Exception ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }

    private static void requireIdentifier(String value, String field) {
        if (value == null || value.isBlank() || value.length() > 96) {
            throw new ExecutionStateException("ELMOS_EXECUTION_" + field.toUpperCase(Locale.ROOT) + "_INVALID");
        }
    }

    private static void requireContext(AuthenticatedContext context) {
        if (context == null) {
            throw new ExecutionStateException("ELMOS_EXECUTION_IDENTITY_CONTEXT_INVALID");
        }
        requireIdentifier(context.organizationId(), "organizationId");
        requireIdentifier(context.accountId(), "accountId");
        requireValue(context.actorId(), 128, "ACTOR_ID");
        requireValue(context.requestId(), 160, "REQUEST_ID");
    }

    private static void requireValue(String value, int max, String field) {
        if (value == null || value.isBlank() || value.length() > max) {
            throw new ExecutionStateException("ELMOS_EXECUTION_" + field + "_INVALID");
        }
    }

    private static void requireWorkload(String workloadClass, int resourceUnits) {
        if (!List.of("PARSING", "GENERATION", "CONVERSION", "VALIDATION", "RENDERING", "MODEL_GPU")
                .contains(workloadClass)
                || resourceUnits < 1 || resourceUnits > 64) {
            throw new ExecutionStateException("ELMOS_EXECUTION_WORKLOAD_PROFILE_INVALID");
        }
    }
}
