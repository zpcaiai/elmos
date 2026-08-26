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
import java.util.regex.Pattern;

/**
 * PostgreSQL 17 adapter for {@link ExecutionJobPort}.
 *
 * <p>Every state transition delegates to the Flyway V57 functions. That is
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
    private static final int MAX_LIST_OFFSET = 10_000;
    private static final Pattern DIGEST_IMAGE =
            Pattern.compile("^[a-z0-9][a-z0-9._/-]*(:[0-9]+)?/?[a-z0-9._/-]*@sha256:[0-9a-f]{64}$");

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
        requireIdentifier(command.jobId(), "jobId");
        return inTenant(command.organizationId(), () -> mapDomainErrors(() ->
                jdbc.sql("""
                        SELECT elmos_enqueue_execution_job(
                            :jobId, :organizationId, :actorId, :businessLine, :jobKind,
                            :idempotencyKey, :requestDigest, cast(:payload AS jsonb),
                            :capability, :image, :priority, :budget, :maxAttempts)
                        """)
                        .param("jobId", command.jobId())
                        .param("organizationId", command.organizationId())
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
                        .query(String.class).single()));
    }

    @Override
    public Optional<JobView> find(String organizationId, String jobId) {
        requireIdentifier(organizationId, "organizationId");
        return inTenant(organizationId, () ->
                jdbc.sql("SELECT * FROM execution_jobs WHERE job_id = :jobId")
                        .param("jobId", jobId)
                        .query(this::readJob)
                        .optional());
    }

    @Override
    public List<JobView> list(String organizationId, BusinessLine businessLine, int limit, int offset) {
        requireIdentifier(organizationId, "organizationId");
        if (limit < 1 || limit > 100) {
            throw new ExecutionStateException("ELMOS_EXECUTION_LIMIT_INVALID");
        }
        if (offset < 0 || offset > MAX_LIST_OFFSET) {
            throw new ExecutionStateException("ELMOS_EXECUTION_OFFSET_INVALID");
        }
        return inTenant(organizationId, () -> {
            // Do not express an absent filter as `:value is null`. PostgreSQL
            // cannot infer the type of a null bind in that arm, and a generic
            // OR predicate also prevents this bounded management query from
            // cleanly using the tenant/business-line ordering index. Both SQL
            // shapes are fixed constants; only values remain parameterized.
            var statement = businessLine == null
                    ? jdbc.sql("""
                            SELECT * FROM execution_jobs
                             ORDER BY created_at DESC
                             LIMIT :limit OFFSET :offset
                            """)
                    : jdbc.sql("""
                            SELECT * FROM execution_jobs
                             WHERE business_line = :businessLine
                             ORDER BY created_at DESC
                             LIMIT :limit OFFSET :offset
                            """)
                            .param("businessLine", businessLine.name());
            return statement
                    .param("limit", limit)
                    .param("offset", offset)
                    .query(this::readJob)
                    .list();
        });
    }

    @Override
    public Status requestCancel(String organizationId, String jobId, String actorId) {
        requireIdentifier(organizationId, "organizationId");
        return inTenant(organizationId, () -> mapDomainErrors(() -> Status.valueOf(
                jdbc.sql("SELECT elmos_request_execution_cancel(:organizationId, :jobId, :actorId)")
                        .param("organizationId", organizationId)
                        .param("jobId", jobId)
                        .param("actorId", actorId)
                        .query(String.class).single())));
    }

    // ---- runner facing -----------------------------------------------------

    @Override
    public List<LeaseGrant> claim(
            String runnerNodeId,
            List<String> capabilities,
            List<String> availableImages,
            int limit,
            int leaseSeconds) {
        int bounded = Math.min(Math.max(limit, 1), 16);
        if (availableImages == null || availableImages.isEmpty()
                || availableImages.size() > 32
                || availableImages.stream().distinct().count() != availableImages.size()
                || availableImages.stream().anyMatch(
                image -> image == null || !DIGEST_IMAGE.matcher(image).matches())) {
            throw new ExecutionStateException("ELMOS_RUNNER_AVAILABLE_IMAGES_INVALID");
        }

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
                    SELECT * FROM elmos_claim_execution_jobs(
                        :runnerNodeId, cast(:capabilities AS text[]),
                        cast(:availableImages AS text[]), :limit, :leaseSeconds,
                        cast(:leaseIds AS text[]), cast(:tokenHashes AS text[]))
                    """)
                    .param("runnerNodeId", runnerNodeId)
                    .param("capabilities", toPgArray(capabilities))
                    .param("availableImages", toPgArray(availableImages))
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
                        SELECT * FROM elmos_heartbeat_execution_lease(
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
                                rs.getObject("lease_expires_at", java.time.OffsetDateTime.class).toInstant()))
                        .single()));
    }

    @Override
    public boolean complete(CompletionCommand command) {
        return transactions.execute(status -> mapDomainErrors(() ->
                jdbc.sql("""
                        SELECT elmos_complete_execution_job(
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
                jdbc.sql("SELECT elmos_reap_execution_leases()").query(Integer.class).single());
    }

    // ---- infrastructure ----------------------------------------------------

    private <T> T inTenant(String organizationId, Supplier<T> work) {
        return transactions.execute(status -> {
            jdbc.sql("SELECT set_config('app.organization_id', :organization, true)")
                    .param("organization", organizationId).query(String.class).single();
            return work.get();
        });
    }

    private JobView readJob(ResultSet rs, int rowNum) throws SQLException {
        return new JobView(
                rs.getString("job_id"),
                rs.getString("organization_id"),
                rs.getString("actor_id"),
                BusinessLine.valueOf(rs.getString("business_line")),
                rs.getString("job_kind"),
                Status.valueOf(rs.getString("status")),
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
     * Translates the {@code ELMOS_*} exceptions raised by the V57 functions into a
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
                int end = tail.indexOf(' ');
                throw new ExecutionStateException(end > 0 ? tail.substring(0, end) : tail);
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
}
