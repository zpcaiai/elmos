package io.elmos.persistence;

import io.elmos.commercial.PlatformAdminPort;
import org.springframework.jdbc.core.simple.JdbcClient;

import java.math.BigDecimal;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.util.List;
import java.util.Objects;

/**
 * PostgreSQL adapter for the platform administration surface.
 *
 * <h2>Why a read returns rows but no decision</h2>
 *
 * <p>The V75 read functions return zero rows when they refuse, and the refusal
 * code only exists in the audit log. Rather than read the log back to find out
 * what just happened -- a second query whose answer could race another request
 * from the same administrator -- this adapter asks the authorization question
 * once, up front, through the same function the reads use. That call is itself
 * audited, so the trail records the attempt whether or not the read followed.
 *
 * <p>The cost is one extra audit row per allowed read. That is the correct
 * direction to be wrong in: an access log with a duplicate is readable, an
 * access log that omits refusals is not evidence of anything.
 */
public final class JdbcPlatformAdminStore implements PlatformAdminPort {

    private final JdbcClient jdbc;

    public JdbcPlatformAdminStore(JdbcClient jdbc) {
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
    }

    @Override
    public String resolveAdminAccount(String organizationId, String actorId) {
        if (organizationId == null || organizationId.isBlank()
                || actorId == null || actorId.isBlank()) {
            return null;
        }
        return jdbc.sql("SELECT elmos_platform_resolve_admin_account(?, ?)")
                .params(organizationId, actorId)
                .query(String.class).optional().orElse(null);
    }

    @Override
    public Page<WalletRow> wallets(String adminAccountId, String afterOrganizationId, int limit) {
        Decision decision = authorize(adminAccountId, "PLATFORM_VIEWER", "WALLET_OVERVIEW", null, null);
        if (!decision.allowed()) {
            return Page.denied(decision);
        }
        List<WalletRow> rows = jdbc.sql("""
                        SELECT organization_id, display_name, currency, balance_minor,
                               reserved_minor, spendable_minor, wallet_status,
                               held_reservations, updated_at
                          FROM elmos_platform_wallet_overview(?, ?, ?)
                        """)
                .params(adminAccountId, afterOrganizationId, bounded(limit, 200))
                .query((ResultSet rs, int row) -> new WalletRow(
                        rs.getString("organization_id"),
                        rs.getString("display_name"),
                        rs.getString("currency"),
                        rs.getBigDecimal("balance_minor"),
                        rs.getBigDecimal("reserved_minor"),
                        rs.getBigDecimal("spendable_minor"),
                        rs.getString("wallet_status"),
                        rs.getLong("held_reservations"),
                        instant(rs, "updated_at")))
                .list();
        return new Page<>(Decision.ALLOWED, rows);
    }

    @Override
    public Page<LedgerRow> ledger(String adminAccountId, String organizationId,
                                  int limit, int offset) {
        Decision decision = authorize(adminAccountId, "PLATFORM_VIEWER", "WALLET_LEDGER",
                organizationId, null);
        if (!decision.allowed()) {
            return Page.denied(decision);
        }
        List<LedgerRow> rows = jdbc.sql("""
                        SELECT entry_id, seq, direction, amount_minor, balance_after_minor,
                               entry_type, source_type, source_ref, actor_id, reason, occurred_at
                          FROM elmos_platform_wallet_ledger(?, ?, ?, ?)
                        """)
                .params(adminAccountId, organizationId, bounded(limit, 200), Math.max(0, offset))
                .query((ResultSet rs, int row) -> new LedgerRow(
                        rs.getString("entry_id"),
                        rs.getLong("seq"),
                        rs.getString("direction"),
                        rs.getBigDecimal("amount_minor"),
                        rs.getBigDecimal("balance_after_minor"),
                        rs.getString("entry_type"),
                        rs.getString("source_type"),
                        rs.getString("source_ref"),
                        rs.getString("actor_id"),
                        rs.getString("reason"),
                        instant(rs, "occurred_at")))
                .list();
        return new Page<>(Decision.ALLOWED, rows);
    }

    @Override
    public Page<TopupRow> topups(String adminAccountId, String statusFilter, int limit) {
        Decision decision = authorize(adminAccountId, "PLATFORM_VIEWER", "TOPUP_ORDERS",
                null, statusFilter);
        if (!decision.allowed()) {
            return Page.denied(decision);
        }
        List<TopupRow> rows = jdbc.sql("""
                        SELECT topup_order_id, organization_id, actor_id, amount_minor,
                               provider, out_trade_no, status, created_at, paid_at, credited_at
                          FROM elmos_platform_topup_orders(?, ?, ?)
                        """)
                .params(adminAccountId, statusFilter, bounded(limit, 200))
                .query((ResultSet rs, int row) -> new TopupRow(
                        rs.getString("topup_order_id"),
                        rs.getString("organization_id"),
                        rs.getString("actor_id"),
                        rs.getBigDecimal("amount_minor"),
                        rs.getString("provider"),
                        rs.getString("out_trade_no"),
                        rs.getString("status"),
                        instant(rs, "created_at"),
                        instant(rs, "paid_at"),
                        instant(rs, "credited_at")))
                .list();
        return new Page<>(Decision.ALLOWED, rows);
    }

    @Override
    public Page<JobRow> jobs(String adminAccountId, String statusFilter,
                             String organizationFilter, int limitPerOrganization) {
        Decision decision = authorize(adminAccountId, "PLATFORM_VIEWER", "JOB_OVERVIEW",
                organizationFilter, statusFilter);
        if (!decision.allowed()) {
            return Page.denied(decision);
        }
        List<JobRow> rows = jdbc.sql("""
                        SELECT job_id, organization_id, business_line, job_kind, status,
                               result_status, failure_code, created_at, started_at,
                               finished_at, settled_amount_minor, hold_status
                          FROM elmos_platform_job_overview(?, ?, ?, ?)
                        """)
                .params(adminAccountId, statusFilter, organizationFilter,
                        bounded(limitPerOrganization, 200))
                .query((ResultSet rs, int row) -> new JobRow(
                        rs.getString("job_id"),
                        rs.getString("organization_id"),
                        rs.getString("business_line"),
                        rs.getString("job_kind"),
                        rs.getString("status"),
                        rs.getString("result_status"),
                        rs.getString("failure_code"),
                        instant(rs, "created_at"),
                        instant(rs, "started_at"),
                        instant(rs, "finished_at"),
                        rs.getBigDecimal("settled_amount_minor"),
                        rs.getString("hold_status")))
                .list();
        return new Page<>(Decision.ALLOWED, rows);
    }

    /**
     * The only cross-tenant write. Note there is no pre-authorization call here:
     * the V75 function performs its own check and returns the decision, so
     * asking twice would produce two audit rows for one act and risk the second
     * check disagreeing with the first.
     */
    @Override
    public AdjustResult adjust(String adminAccountId, String organizationId, String direction,
                               BigDecimal amountMinor, String reason, String idempotencyKey) {
        return jdbc.sql("SELECT status, entry_id FROM elmos_platform_wallet_adjust(?, ?, ?, ?, ?, ?)")
                .params(adminAccountId, organizationId, direction, amountMinor,
                        reason, idempotencyKey)
                .query((ResultSet rs, int row) -> new AdjustResult(
                        Decision.parse(rs.getString("status")),
                        rs.getString("entry_id")))
                .single();
    }

    @Override
    public Decision grant(String adminAccountId, String targetAccountId,
                          String platformRole, String reason) {
        return Decision.parse(jdbc
                .sql("SELECT elmos_platform_grant_admin(?, ?, ?, ?)")
                .params(adminAccountId, targetAccountId, platformRole, reason)
                .query(String.class).single());
    }

    @Override
    public Decision revoke(String adminAccountId, String targetAccountId, String reason) {
        return Decision.parse(jdbc
                .sql("SELECT elmos_platform_revoke_admin(?, ?, ?)")
                .params(adminAccountId, targetAccountId, reason)
                .query(String.class).single());
    }

    private Decision authorize(String adminAccountId, String requiredRole, String operation,
                               String targetOrganizationId, String targetRef) {
        return Decision.parse(jdbc
                .sql("SELECT elmos_platform_authorize(?, ?, ?, ?, ?)")
                .params(adminAccountId, requiredRole, operation, targetOrganizationId, targetRef)
                .query(String.class).single());
    }

    private static int bounded(int value, int max) {
        return Math.max(1, Math.min(value, max));
    }

    private static Instant instant(ResultSet rs, String column) throws SQLException {
        var timestamp = rs.getTimestamp(column);
        return timestamp == null ? null : timestamp.toInstant();
    }
}
