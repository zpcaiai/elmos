package io.elmos.persistence;

import io.elmos.commercial.WalletPort;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.support.TransactionTemplate;

import java.math.BigDecimal;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.function.Supplier;

/**
 * PostgreSQL adapter for the prepaid wallet.
 *
 * <h2>Why almost every method is a function call</h2>
 *
 * <p>The V73 accounting functions hold the wallet row lock, write the ledger and
 * move the balance in one statement. Reimplementing any part of that here would
 * create a second place where money changes, and the two would agree until the
 * day one of them was edited. This adapter therefore translates arguments and
 * error codes; it never computes a balance.
 *
 * <h2>Why the reads open a transaction</h2>
 *
 * <p>The wallet tables are FORCE ROW LEVEL SECURITY. The write path is safe
 * without help -- each V73 function binds the tenant it was given -- but a plain
 * {@code SELECT} from this adapter runs under whatever context the connection
 * happens to carry, which on a pooled connection is nothing. That returns zero
 * rows rather than an error, so the failure would look like "this tenant has no
 * wallet". Every direct read is wrapped in a transaction that binds the tenant
 * first, and {@code set_config(..., true)} keeps the binding from outliving it.
 */
public final class JdbcWalletStore implements WalletPort {

    private final JdbcClient jdbc;
    private final TransactionTemplate transactions;

    public JdbcWalletStore(JdbcClient jdbc, TransactionTemplate transactions) {
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
        this.transactions = Objects.requireNonNull(transactions, "transactions");
    }

    // ------------------------------------------------------------------
    // Reads
    // ------------------------------------------------------------------

    @Override
    public WalletBalance balance(String organizationId) {
        return inTenant(organizationId, () -> jdbc.sql("""
                        SELECT organization_id, currency, balance_minor, reserved_minor,
                               status, updated_at
                          FROM wallet_accounts
                         WHERE organization_id = ?
                        """)
                .param(organizationId)
                .query((ResultSet rs, int row) -> new WalletBalance(
                        rs.getString("organization_id"),
                        rs.getString("currency"),
                        rs.getBigDecimal("balance_minor"),
                        rs.getBigDecimal("reserved_minor"),
                        rs.getBigDecimal("balance_minor").subtract(rs.getBigDecimal("reserved_minor")),
                        rs.getString("status"),
                        instant(rs, "updated_at")))
                .optional()
                // A tenant with no wallet row yet is not an error; it is a tenant
                // that has never topped up. Reporting zero keeps every caller from
                // having to special-case "before the first payment".
                .orElseGet(() -> new WalletBalance(
                        organizationId, "CNY", BigDecimal.ZERO, BigDecimal.ZERO,
                        BigDecimal.ZERO, "ACTIVE", null)));
    }

    @Override
    public List<LedgerEntry> ledger(String organizationId, int limit, int offset) {
        int boundedLimit = Math.max(1, Math.min(limit, 200));
        int boundedOffset = Math.max(0, offset);
        return inTenant(organizationId, () -> jdbc.sql("""
                        SELECT entry_id, seq, direction, amount_minor, balance_after_minor,
                               entry_type, source_type, source_ref, actor_id, reason, occurred_at
                          FROM wallet_ledger_entries
                         WHERE organization_id = ?
                         ORDER BY seq DESC
                         LIMIT ? OFFSET ?
                        """)
                .params(organizationId, boundedLimit, boundedOffset)
                .query((ResultSet rs, int row) -> new LedgerEntry(
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
                .list());
    }

    @Override
    public TopupBounds topupBounds(String organizationId) {
        return call(() -> jdbc.sql(
                        "SELECT min_amount_minor, max_amount_minor, daily_amount_limit_minor"
                                + " FROM elmos_wallet_topup_bounds(?)")
                .param(organizationId)
                .query((ResultSet rs, int row) -> new TopupBounds(
                        rs.getBigDecimal("min_amount_minor"),
                        rs.getBigDecimal("max_amount_minor"),
                        rs.getBigDecimal("daily_amount_limit_minor")))
                .single());
    }

    @Override
    public Optional<TopupOrder> findTopupOrder(String organizationId, String topupOrderId) {
        return inTenant(organizationId, () -> jdbc.sql("""
                        SELECT topup_order_id, organization_id, actor_id, currency, amount_minor,
                               provider, out_trade_no, status, created_at, paid_at,
                               credited_at, expires_at
                          FROM wallet_topup_orders
                         WHERE organization_id = ? AND topup_order_id = ?
                        """)
                .params(organizationId, topupOrderId)
                .query((ResultSet rs, int row) -> new TopupOrder(
                        rs.getString("topup_order_id"),
                        rs.getString("organization_id"),
                        rs.getString("actor_id"),
                        rs.getString("currency"),
                        rs.getBigDecimal("amount_minor"),
                        rs.getString("provider"),
                        rs.getString("out_trade_no"),
                        rs.getString("status"),
                        instant(rs, "created_at"),
                        instant(rs, "paid_at"),
                        instant(rs, "credited_at"),
                        instant(rs, "expires_at")))
                .optional());
    }

    /**
     * The one read that must NOT bind a tenant, because its whole purpose is to
     * find out which tenant to bind. It reads the directory projection, which is
     * deliberately not isolated and carries no customer content.
     */
    @Override
    public Optional<TopupDirectoryEntry> findTopupByOutTradeNo(String outTradeNo) {
        return call(() -> jdbc.sql("""
                        SELECT out_trade_no, topup_order_id, organization_id, amount_minor, status
                          FROM wallet_topup_order_directory
                         WHERE out_trade_no = ?
                           AND status IN ('CREATED', 'PENDING_PAYMENT', 'PAID', 'CREDITED')
                        """)
                .param(outTradeNo)
                .query((ResultSet rs, int row) -> new TopupDirectoryEntry(
                        rs.getString("out_trade_no"),
                        rs.getString("topup_order_id"),
                        rs.getString("organization_id"),
                        rs.getBigDecimal("amount_minor"),
                        rs.getString("status")))
                .optional());
    }

    @Override
    public Optional<Reconciliation> reconcile(String organizationId) {
        return call(() -> jdbc.sql("""
                        SELECT organization_id, projected_balance_minor, ledger_balance_minor,
                               projected_reserved_minor, held_reserved_minor
                          FROM elmos_wallet_reconcile(?)
                        """)
                .param(organizationId)
                .query((ResultSet rs, int row) -> new Reconciliation(
                        rs.getString("organization_id"),
                        rs.getBigDecimal("projected_balance_minor"),
                        rs.getBigDecimal("ledger_balance_minor"),
                        rs.getBigDecimal("projected_reserved_minor"),
                        rs.getBigDecimal("held_reserved_minor")))
                .optional());
    }

    // ------------------------------------------------------------------
    // Writes -- every one of these is a V73 function call
    // ------------------------------------------------------------------

    @Override
    public String createTopupOrder(String topupOrderId, String organizationId, String actorId,
                                   BigDecimal amountMinor, String provider, String outTradeNo,
                                   String idempotencyKey, int ttlSeconds) {
        return call(() -> jdbc.sql(
                        "SELECT elmos_wallet_create_topup_order(?, ?, ?, ?, ?, ?, ?, ?)")
                .params(topupOrderId, organizationId, actorId, amountMinor, provider,
                        outTradeNo, idempotencyKey, ttlSeconds)
                .query(String.class).single());
    }

    @Override
    public String creditTopup(String organizationId, String topupOrderId,
                              String providerTxnRef, String actorId) {
        return call(() -> jdbc.sql("SELECT elmos_wallet_credit_topup(?, ?, ?, ?)")
                .params(organizationId, topupOrderId, providerTxnRef, actorId)
                .query(String.class).single());
    }

    @Override
    public String reserve(String reservationId, String organizationId, String jobId,
                          BigDecimal amountMinor, String quoteRef, String actorId,
                          int ttlSeconds) {
        return call(() -> jdbc.sql("SELECT elmos_wallet_reserve(?, ?, ?, ?, ?, ?, ?)")
                .params(reservationId, organizationId, jobId, amountMinor, quoteRef,
                        actorId, ttlSeconds)
                .query(String.class).single());
    }

    @Override
    public void settle(String organizationId, String jobId, BigDecimal settledAmountMinor,
                       String actorId, String resolutionCode) {
        call(() -> jdbc.sql("SELECT elmos_wallet_settle(?, ?, ?, ?, ?)")
                .params(organizationId, jobId, settledAmountMinor, actorId, resolutionCode)
                .query(String.class).single());
    }

    @Override
    public void release(String organizationId, String jobId, String resolutionCode) {
        call(() -> jdbc.sql("SELECT elmos_wallet_release(?, ?, ?)")
                .params(organizationId, jobId, resolutionCode)
                .query(String.class).single());
    }

    @Override
    public int expireReservations(String organizationId, int limit) {
        return call(() -> jdbc.sql("SELECT elmos_wallet_expire_reservations(?, ?)")
                .params(organizationId, Math.max(1, Math.min(limit, 1000)))
                .query(Integer.class).single());
    }

    @Override
    public String adjust(String organizationId, String direction, BigDecimal amountMinor,
                         String actorId, String reason, String idempotencyKey) {
        return call(() -> jdbc.sql("SELECT elmos_wallet_adjust(?, ?, ?, ?, ?, ?)")
                .params(organizationId, direction, amountMinor, actorId, reason, idempotencyKey)
                .query(String.class).single());
    }

    // ------------------------------------------------------------------
    // Plumbing
    // ------------------------------------------------------------------

    private <T> T inTenant(String organizationId, Supplier<T> work) {
        if (organizationId == null || organizationId.isBlank()) {
            throw new WalletStateException("ELMOS_WALLET_TENANT_REQUIRED", "组织未提供。");
        }
        return call(() -> transactions.execute(status -> {
            jdbc.sql("SELECT set_config('app.organization_id', ?, true)")
                    .param(organizationId).query(String.class).single();
            return work.get();
        }));
    }

    /**
     * Turns a PostgreSQL {@code RAISE EXCEPTION 'ELMOS_WALLET_...'} back into a
     * code the caller can branch on.
     *
     * <p>Matching on the message is unpleasant, but the alternative -- mapping
     * every refusal to one opaque failure -- would make "you need to top up"
     * indistinguishable from "the database is down", and those deserve very
     * different responses. The codes are stable identifiers chosen in V73 for
     * exactly this, and the migration contract test guards them.
     */
    private <T> T call(Supplier<T> work) {
        try {
            return work.get();
        } catch (WalletStateException already) {
            throw already;
        } catch (RuntimeException failure) {
            String code = walletCode(failure);
            if (code != null) {
                throw new WalletStateException(code, code, failure);
            }
            throw failure;
        }
    }

    static String walletCode(Throwable failure) {
        for (Throwable cause = failure; cause != null; cause = cause.getCause()) {
            String message = cause.getMessage();
            if (message == null) {
                continue;
            }
            int start = message.indexOf("ELMOS_WALLET_");
            if (start < 0) {
                continue;
            }
            int end = start;
            while (end < message.length()
                    && (Character.isLetterOrDigit(message.charAt(end)) || message.charAt(end) == '_')) {
                end++;
            }
            return message.substring(start, end);
        }
        return null;
    }

    private static Instant instant(ResultSet rs, String column) throws SQLException {
        var timestamp = rs.getTimestamp(column);
        return timestamp == null ? null : timestamp.toInstant();
    }
}
