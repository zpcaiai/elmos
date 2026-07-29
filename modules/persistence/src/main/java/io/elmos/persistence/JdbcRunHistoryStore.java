package io.elmos.persistence;

import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.function.Supplier;

/**
 * Read-only reconstruction of a single migration run's history.
 *
 * <p>This is the other half of the audit loop. The export answers "what
 * happened across the tenant"; a replay answers "what happened to this one run,
 * in order, and what evidence was produced along the way". An auditor asking
 * the second question is reconstructing a past decision, so the reconstruction
 * must not be able to change what it is reconstructing.
 *
 * <p>That property is enforced by the database, not by convention. Every read
 * runs inside a transaction marked read-only, so PostgreSQL refuses any write
 * issued from this class -- including one added later by someone who did not
 * read this comment. A promise in prose would hold exactly until the first
 * person appended an {@code update}; a read-only transaction holds regardless.
 * Binding the tenant with {@code set_config} is still permitted, because
 * setting a run-time parameter is not a write to data.
 *
 * <p>Each section is read one row beyond its cap and reports {@code truncated}
 * rather than quietly returning a short list. A replay that silently omits the
 * attempt where the run failed is worse than one that admits it is incomplete.
 */
@Repository
public final class JdbcRunHistoryStore {

    /**
     * Generous enough that a real run never reaches it, small enough that a
     * pathological one cannot exhaust the heap. Reaching it is reported, never
     * hidden.
     */
    private static final int DEFAULT_SECTION_CAP = 2_000;

    private final JdbcClient jdbc;
    private final TransactionTemplate readOnly;
    private final int sectionCap;

    public JdbcRunHistoryStore(JdbcClient jdbc, PlatformTransactionManager transactionManager) {
        this(jdbc, transactionManager, DEFAULT_SECTION_CAP);
    }

    /**
     * Package-private so a test can drive the truncation branch with a cap it
     * can actually reach. An untested truncation flag is the same hazard as no
     * flag at all: nobody finds out it is wired backwards until the one replay
     * that overflows, which is exactly the replay somebody needed.
     */
    JdbcRunHistoryStore(JdbcClient jdbc, PlatformTransactionManager transactionManager, int sectionCap) {
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
        Objects.requireNonNull(transactionManager, "transactionManager");
        if (sectionCap < 1) throw new IllegalArgumentException("sectionCap must be positive");
        this.sectionCap = sectionCap;
        TransactionTemplate template = new TransactionTemplate(transactionManager);
        template.setReadOnly(true);
        this.readOnly = template;
    }

    /** One attempt at one step. Attempts are kept, not collapsed: a run that succeeded on the third try is a different story from one that succeeded on the first. */
    public record StepAttempt(
            String stepRunId,
            String stepId,
            int attempt,
            String executorType,
            String state,
            Instant startedAt,
            Instant finishedAt,
            String failureCode
    ) {}

    /** An evidence record produced during the run, tied to a step when the producer knew which one. */
    public record EvidenceRef(
            String evidenceId,
            String stepRunId,
            String evidenceType,
            String producerType,
            String producerName,
            String producerVersion,
            String status,
            String summary,
            String artifactRef,
            String contentHash,
            Instant createdAt
    ) {}

    /** An audit row naming this run as its resource. */
    public record AuditEntry(
            String auditId,
            String actorType,
            String actorId,
            String action,
            String resourceType,
            Instant occurredAt,
            String policyDecision,
            String result,
            String requestId
    ) {}

    public record Section<T>(List<T> rows, boolean truncated) {}

    public record RunTimeline(
            String migrationRunId,
            String organizationId,
            String snapshotId,
            String migrationPlanId,
            int planVersion,
            String state,
            Section<StepAttempt> steps,
            Section<EvidenceRef> evidence,
            Section<AuditEntry> audit
    ) {}

    /**
     * Reconstructs one run, or empty when the tenant has no such run.
     *
     * <p>Empty rather than an exception for a missing run, because "no such run
     * for this tenant" and "run belongs to another tenant" must be
     * indistinguishable to the caller. Row-level security already hides the
     * second case; returning empty for both keeps a probe from learning that a
     * run id exists somewhere else.
     */
    public Optional<RunTimeline> replay(String organizationId, String migrationRunId) {
        requireIdentifier(organizationId, "organizationId");
        requireIdentifier(migrationRunId, "migrationRunId");
        return inTenant(organizationId, () -> {
            List<Header> header = jdbc.sql("""
                    select migration_run_id, organization_id, snapshot_id,
                           migration_plan_id, plan_version, state
                      from migration_runs
                     where organization_id = :organization
                       and migration_run_id = :run
                    """)
                    .param("organization", organizationId).param("run", migrationRunId)
                    .query(JdbcRunHistoryStore::mapHeader)
                    .list();
            if (header.isEmpty()) return Optional.empty();
            Header run = header.get(0);

            // Ordered by the clock first so the timeline reads as one, with
            // step and attempt breaking ties. started_at is nullable -- a step
            // that never began still belongs in the story, at the end.
            Section<StepAttempt> steps = section(jdbc.sql("""
                    select step_run_id, step_id, attempt, executor_type, state,
                           started_at, finished_at, failure_code
                      from migration_step_runs
                     where migration_run_id = :run
                     order by started_at asc nulls last, step_id asc, attempt asc
                     limit :limit
                    """)
                    .param("run", migrationRunId).param("limit", sectionCap + 1)
                    .query(JdbcRunHistoryStore::mapStep)
                    .list());

            Section<EvidenceRef> evidence = section(jdbc.sql("""
                    select evidence_id, step_run_id, evidence_type, producer_type,
                           producer_name, producer_version, status, summary,
                           artifact_ref, content_hash, created_at
                      from evidence
                     where organization_id = :organization
                       and migration_run_id = :run
                     order by created_at asc, evidence_id asc
                     limit :limit
                    """)
                    .param("organization", organizationId).param("run", migrationRunId)
                    .param("limit", sectionCap + 1)
                    .query(JdbcRunHistoryStore::mapEvidence)
                    .list());

            // audit_events carries no migration_run_id column; the run is named
            // through the generic resource_id. That is the only join the schema
            // offers, so it is the one used -- and it is why an audit row that
            // forgot to set resource_id is invisible here rather than silently
            // attributed somewhere wrong.
            Section<AuditEntry> audit = section(jdbc.sql("""
                    select audit_id, actor_type, actor_id, action, resource_type,
                           occurred_at, policy_decision, result, request_id
                      from audit_events
                     where organization_id = :organization
                       and resource_id = :run
                     order by occurred_at asc, audit_id asc
                     limit :limit
                    """)
                    .param("organization", organizationId).param("run", migrationRunId)
                    .param("limit", sectionCap + 1)
                    .query(JdbcRunHistoryStore::mapAudit)
                    .list());

            return Optional.of(new RunTimeline(
                    run.migrationRunId(), run.organizationId(), run.snapshotId(),
                    run.migrationPlanId(), run.planVersion(), run.state(),
                    steps, evidence, audit));
        });
    }

    private <T> Section<T> section(List<T> rows) {
        boolean truncated = rows.size() > sectionCap;
        return new Section<>(truncated ? List.copyOf(rows.subList(0, sectionCap)) : List.copyOf(rows), truncated);
    }

    private record Header(
            String migrationRunId,
            String organizationId,
            String snapshotId,
            String migrationPlanId,
            int planVersion,
            String state
    ) {}

    private static Header mapHeader(ResultSet rs, int row) throws SQLException {
        return new Header(
                rs.getString("migration_run_id"),
                rs.getString("organization_id"),
                rs.getString("snapshot_id"),
                rs.getString("migration_plan_id"),
                rs.getInt("plan_version"),
                rs.getString("state"));
    }

    private static StepAttempt mapStep(ResultSet rs, int row) throws SQLException {
        return new StepAttempt(
                rs.getString("step_run_id"),
                rs.getString("step_id"),
                rs.getInt("attempt"),
                rs.getString("executor_type"),
                rs.getString("state"),
                instant(rs.getObject("started_at", OffsetDateTime.class)),
                instant(rs.getObject("finished_at", OffsetDateTime.class)),
                rs.getString("failure_code"));
    }

    private static EvidenceRef mapEvidence(ResultSet rs, int row) throws SQLException {
        return new EvidenceRef(
                rs.getString("evidence_id"),
                rs.getString("step_run_id"),
                rs.getString("evidence_type"),
                rs.getString("producer_type"),
                rs.getString("producer_name"),
                rs.getString("producer_version"),
                rs.getString("status"),
                rs.getString("summary"),
                rs.getString("artifact_ref"),
                rs.getString("content_hash"),
                instant(rs.getObject("created_at", OffsetDateTime.class)));
    }

    private static AuditEntry mapAudit(ResultSet rs, int row) throws SQLException {
        return new AuditEntry(
                rs.getString("audit_id"),
                rs.getString("actor_type"),
                rs.getString("actor_id"),
                rs.getString("action"),
                rs.getString("resource_type"),
                instant(rs.getObject("occurred_at", OffsetDateTime.class)),
                rs.getString("policy_decision"),
                rs.getString("result"),
                rs.getString("request_id"));
    }

    private static Instant instant(OffsetDateTime value) {
        return value == null ? null : value.toInstant();
    }

    private <T> T inTenant(String organizationId, Supplier<T> work) {
        return readOnly.execute(status -> {
            jdbc.sql("select set_config('app.organization_id', :organization, true)")
                    .param("organization", organizationId).query(String.class).single();
            return work.get();
        });
    }

    private static void requireIdentifier(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " is required");
        }
        if (value.length() > 128) {
            throw new IllegalArgumentException(field + " must be at most 128 characters");
        }
    }
}
