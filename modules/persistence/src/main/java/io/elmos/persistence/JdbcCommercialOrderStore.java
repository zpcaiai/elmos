package io.elmos.persistence;

import io.elmos.commercial.CommercialOrderPort;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.support.TransactionTemplate;

import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.function.Supplier;

import static io.elmos.persistence.SqlTimestamps.offset;

/** PostgreSQL adapter for V83 commercial orders and credits. */
public final class JdbcCommercialOrderStore implements CommercialOrderPort {
    private final JdbcClient jdbc;
    private final TransactionTemplate transactions;

    public JdbcCommercialOrderStore(JdbcClient jdbc, TransactionTemplate transactions) {
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
        this.transactions = Objects.requireNonNull(transactions, "transactions");
    }

    @Override
    public String createOrder(String orderId, String organizationId, String actorId,
                              String sku, String projectId, String provider, String outTradeNo,
                              String idempotencyKey, String requestHash, int ttlSeconds) {
        return inTenant(organizationId, () -> jdbc.sql("""
                select elmos_commercial_create_order(
                    :orderId, :actor, :sku, :project, :provider, :trade,
                    :idempotency, cast(:requestHash as char(64)), :ttl)
                """).param("orderId", orderId).param("actor", actorId).param("sku", sku)
                .param("project", projectId).param("provider", provider).param("trade", outTradeNo)
                .param("idempotency", idempotencyKey).param("requestHash", requestHash)
                .param("ttl", ttlSeconds).query(String.class).single());
    }

    @Override
    public Optional<Order> findOrder(String organizationId, String orderId) {
        return inTenant(organizationId, () -> jdbc.sql("""
                select * from commercial_orders
                 where organization_id = :organization and order_id = :order
                """).param("organization", organizationId).param("order", orderId)
                .query(this::order).optional());
    }

    @Override
    public String markOrderAwaitingPayment(
            String organizationId, String actorId, String orderId) {
        return inTenant(organizationId, () -> jdbc.sql(
                        "select elmos_commercial_mark_order_handoff(:order, :actor)")
                .param("order", orderId).param("actor", actorId)
                .query(String.class).single());
    }

    @Override
    public String markOrderPreparationFailed(
            String organizationId, String actorId, String orderId,
            boolean outcomeUnknown, String failureCode) {
        return inTenant(organizationId, () -> jdbc.sql("""
                select elmos_commercial_mark_order_prepare_failed(
                    :order, :actor, :unknown, :failure)
                """).param("order", orderId).param("actor", actorId)
                .param("unknown", outcomeUnknown).param("failure", failureCode)
                .query(String.class).single());
    }

    @Override
    public List<Order> orders(String organizationId, String actorId, int limit, int offsetValue,
                              boolean organizationScope) {
        requirePage(limit, offsetValue);
        String actorClause = organizationScope ? "" : " and actor_id = :actor";
        var spec = jdbc.sql("""
                select * from commercial_orders
                 where organization_id = :organization%s
                 order by created_at desc, order_id desc limit :limit offset :offset
                """.formatted(actorClause)).param("organization", organizationId)
                .param("limit", limit).param("offset", offsetValue);
        if (!organizationScope) spec = spec.param("actor", actorId);
        var query = spec;
        return inTenant(organizationId, () -> query.query(this::order).list());
    }

    @Override
    public CreditBalance creditBalance(String organizationId) {
        return inTenant(organizationId, () -> {
            expireGenerationReservations();
            return jdbc.sql("""
                select a.organization_id,
                       coalesce(sum(l.available + l.reserved)
                           filter (where l.expires_at > now() or l.reserved > 0), 0) balance,
                       coalesce(sum(l.reserved), 0) reserved,
                       coalesce(sum(l.available) filter (where l.expires_at > now()), 0) spendable,
                       a.status
                  from commercial_credit_accounts a
                  left join commercial_credit_lots l on l.organization_id = a.organization_id
                 where a.organization_id = :organization
                 group by a.organization_id, a.status
                """).param("organization", organizationId)
                .query((rs, row) -> new CreditBalance(
                        rs.getString("organization_id"), rs.getBigDecimal("balance"),
                        rs.getBigDecimal("reserved"), rs.getBigDecimal("spendable"),
                        rs.getString("status")))
                .optional().orElse(new CreditBalance(
                        organizationId, BigDecimal.ZERO, BigDecimal.ZERO, BigDecimal.ZERO, "ACTIVE"));
        });
    }

    @Override
    public List<CreditLedgerEntry> creditLedger(String organizationId, String actorId,
                                                 int limit, int offsetValue,
                                                 boolean organizationScope) {
        requirePage(limit, offsetValue);
        String actorClause = organizationScope ? "" : " and actor_id = :actor";
        var spec = jdbc.sql("""
                select * from commercial_credit_ledger_entries
                 where organization_id = :organization%s
                 order by occurred_at desc, ledger_entry_id desc limit :limit offset :offset
                """.formatted(actorClause)).param("organization", organizationId)
                .param("limit", limit).param("offset", offsetValue);
        if (!organizationScope) spec = spec.param("actor", actorId);
        var query = spec;
        return inTenant(organizationId, () -> query.query((rs, row) -> new CreditLedgerEntry(
                rs.getString("ledger_entry_id"), rs.getString("actor_id"),
                rs.getString("direction"), rs.getBigDecimal("quantity"),
                rs.getBigDecimal("balance_after"), rs.getString("entry_type"),
                rs.getString("source_order_id"), rs.getString("project_id"),
                rs.getString("job_id"), SqlTimestamps.instant(rs.getObject("expires_at", OffsetDateTime.class)),
                SqlTimestamps.instant(rs.getObject("occurred_at", OffsetDateTime.class)))).list());
    }

    @Override
    public GenerationReservation reserveGeneration(String reservationId, String organizationId,
                                                   String actorId, String projectId, String jobId,
                                                   BigDecimal requestedCredits,
                                                   String idempotencyKey, int ttlSeconds) {
        return inTenant(organizationId, () -> {
            expireGenerationReservations();
            return jdbc.sql("""
                select * from elmos_commercial_reserve_generation(
                    :reservation, :actor, :project, :job, :credits, :idempotency, :ttl)
                """).param("reservation", reservationId).param("actor", actorId)
                .param("project", projectId).param("job", jobId).param("credits", requestedCredits)
                .param("idempotency", idempotencyKey).param("ttl", ttlSeconds)
                .query((rs, row) -> new GenerationReservation(
                        rs.getString("reservation_id"), rs.getString("decision"),
                        rs.getString("funding_source"), rs.getBigDecimal("remaining_credits")))
                .single();
        });
    }

    @Override
    public String settleGeneration(String organizationId, String actorId,
                                   String reservationId, BigDecimal actualCredits) {
        return inTenant(organizationId, () -> {
            expireGenerationReservations();
            return jdbc.sql(
                "select elmos_commercial_settle_generation(:reservation, :actor, :credits)")
                .param("reservation", reservationId).param("actor", actorId)
                .param("credits", actualCredits).query(String.class).single();
        });
    }

    @Override
    public String releaseGeneration(String organizationId, String actorId, String reservationId) {
        return inTenant(organizationId, () -> {
            expireGenerationReservations();
            return jdbc.sql(
                "select elmos_commercial_release_generation(:reservation, :actor)")
                .param("reservation", reservationId).param("actor", actorId)
                .query(String.class).single();
        });
    }

    private void expireGenerationReservations() {
        jdbc.sql("select elmos_commercial_expire_generation_reservations(1000)")
                .query(Integer.class).single();
    }

    private Order order(java.sql.ResultSet rs, int row) throws java.sql.SQLException {
        return new Order(rs.getString("order_id"), rs.getString("organization_id"),
                rs.getString("actor_id"), rs.getString("order_type"), rs.getString("sku"),
                rs.getString("catalog_version"), rs.getString("project_id"),
                rs.getString("currency"), rs.getBigDecimal("amount_minor"),
                rs.getBigDecimal("credit_quantity"), rs.getString("provider"),
                rs.getString("out_trade_no"), rs.getString("status"),
                SqlTimestamps.instant(rs.getObject("created_at", OffsetDateTime.class)),
                SqlTimestamps.instant(rs.getObject("expires_at", OffsetDateTime.class)),
                SqlTimestamps.instant(rs.getObject("paid_at", OffsetDateTime.class)),
                SqlTimestamps.instant(rs.getObject("fulfilled_at", OffsetDateTime.class)),
                rs.getString("failure_code"));
    }

    private <T> T inTenant(String organizationId, Supplier<T> work) {
        return transactions.execute(status -> {
            jdbc.sql("select set_config('app.organization_id', :organization, true)")
                    .param("organization", organizationId).query(String.class).single();
            return work.get();
        });
    }

    private static void requirePage(int limit, int offsetValue) {
        if (limit < 1 || limit > 200 || offsetValue < 0) {
            throw new IllegalArgumentException("invalid page");
        }
    }
}
