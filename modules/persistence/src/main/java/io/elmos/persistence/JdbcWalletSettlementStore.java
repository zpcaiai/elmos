package io.elmos.persistence;

import io.elmos.commercial.WalletSettlementPort;
import org.springframework.jdbc.core.simple.JdbcClient;

import java.math.BigDecimal;
import java.sql.ResultSet;
import java.util.List;
import java.util.Objects;

/**
 * PostgreSQL adapter for the settlement loop.
 *
 * <p>No transaction template and no tenant binding here, unlike
 * {@link JdbcWalletStore}. Every call is a single V74 function that either
 * needs no tenant (the outbox is not isolated, by the same reasoning as
 * execution_job_dispatch) or binds the one it was given
 * ({@code elmos_wallet_settlement_facts}). Adding a binding at this layer would
 * be a second place that decides which tenant a settler is looking at.
 */
public final class JdbcWalletSettlementStore implements WalletSettlementPort {

    private final JdbcClient jdbc;

    public JdbcWalletSettlementStore(JdbcClient jdbc) {
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
    }

    @Override
    public List<Claim> claim(int limit, int leaseSeconds) {
        return jdbc.sql("""
                        SELECT outbox_id, organization_id, job_id, reservation_id,
                               job_status, failure_code, attempts
                          FROM elmos_wallet_claim_settlements(?, ?)
                        """)
                .params(Math.max(1, Math.min(limit, 500)), Math.max(30, leaseSeconds))
                .query((ResultSet rs, int row) -> new Claim(
                        rs.getString("outbox_id"),
                        rs.getString("organization_id"),
                        rs.getString("job_id"),
                        rs.getString("reservation_id"),
                        rs.getString("job_status"),
                        rs.getString("failure_code"),
                        rs.getInt("attempts")))
                .list();
    }

    /**
     * @return null when the job is gone. The service treats that as "release",
     *         which is why this returns null rather than raising: a vanished job
     *         is a resolvable situation, not an error to retry forever.
     */
    @Override
    public JobFacts facts(String organizationId, String jobId) {
        return jdbc.sql("""
                        SELECT status, failure_code, business_line, job_kind,
                               budget_wall_seconds, elapsed_seconds, chargeable_failure
                          FROM elmos_wallet_settlement_facts(?, ?)
                        """)
                .params(organizationId, jobId)
                .query((ResultSet rs, int row) -> new JobFacts(
                        rs.getString("status"),
                        rs.getString("failure_code"),
                        rs.getString("business_line"),
                        rs.getString("job_kind"),
                        rs.getInt("budget_wall_seconds"),
                        rs.getInt("elapsed_seconds"),
                        rs.getBoolean("chargeable_failure")))
                .optional()
                .orElse(null);
    }

    @Override
    public Quote quote(String businessLine, String jobKind, int budgetWallSeconds) {
        return jdbc.sql("""
                        SELECT quote_ref, reserve_minor, min_charge_minor, unit, unit_price_minor
                          FROM elmos_wallet_quote(?, ?, ?)
                        """)
                .params(businessLine, jobKind, budgetWallSeconds)
                .query((ResultSet rs, int row) -> new Quote(
                        rs.getString("quote_ref"),
                        rs.getBigDecimal("reserve_minor"),
                        rs.getBigDecimal("min_charge_minor"),
                        rs.getString("unit"),
                        rs.getBigDecimal("unit_price_minor")))
                .single();
    }

    @Override
    public boolean resolve(String outboxId, BigDecimal settledAmountMinor,
                           String resolutionCode, String actorId) {
        return Boolean.TRUE.equals(jdbc
                .sql("SELECT elmos_wallet_resolve_settlement(?, ?, ?, ?)")
                .params(outboxId,
                        settledAmountMinor == null ? BigDecimal.ZERO : settledAmountMinor,
                        resolutionCode, actorId)
                .query(Boolean.class).single());
    }

    @Override
    public void fail(String outboxId, String errorCode) {
        jdbc.sql("SELECT elmos_wallet_fail_settlement(?, ?)")
                .params(outboxId, errorCode)
                .query(Object.class).optional();
    }
}
