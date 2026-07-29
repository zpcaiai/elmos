package io.elmos.commercialadapter.payment;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.HexFormat;
import javax.sql.DataSource;

/**
 * 回调管线三个端口的 PostgreSQL 实现。对应迁移 V54。
 *
 * <p>只依赖 JDK 的 {@code java.sql} / {@code javax.sql}，不引入 ORM：
 * 这三段 SQL 的并发语义是正确性的关键，藏在 ORM 后面反而看不清。
 */
public final class JdbcCallbackPorts {

    private JdbcCallbackPorts() {
    }

    // -----------------------------------------------------------------------
    // 第 2 步 · 幂等去重
    // -----------------------------------------------------------------------

    /**
     * 基于主键冲突的原子登记。
     *
     * <p><b>绝不能改成"先 SELECT 再 INSERT"。</b>已在 PostgreSQL 16.13 上实测：
     * 两个并发会话的 SELECT 都会看到 0 行，于是都判定"首次见到"；
     * 唯一约束只能在 INSERT 阶段兜住其中一个，而业务判断此时已经做出。
     * 若实现吞掉那个 duplicate key 异常并返回 {@code true}，
     * 重复回调就会被当成首次处理，导致重复发放额度。
     *
     * <p>{@code ON CONFLICT DO NOTHING ... RETURNING} 把"判定"与"登记"
     * 合并成一条语句：20 个并发会话争同一个键时，实测恰好 1 个拿到返回行。
     */
    public static PaymentCallbackPipeline.ProcessedEventLog processedEventLog(DataSource source) {
        return idempotencyKey -> {
            String[] parts = splitKey(idempotencyKey);
            String sql = """
                    INSERT INTO payment_callback_receipts (provider, provider_event_id)
                    VALUES (?, ?)
                    ON CONFLICT (provider, provider_event_id) DO NOTHING
                    RETURNING provider_event_id
                    """;
            try (Connection connection = source.getConnection();
                 PreparedStatement statement = connection.prepareStatement(sql)) {
                statement.setString(1, parts[0]);
                statement.setString(2, parts[1]);
                try (ResultSet rows = statement.executeQuery()) {
                    // 有返回行 = 本次调用赢得了登记 = 首次见到
                    return rows.next();
                }
            } catch (SQLException failure) {
                // 登记失败绝不能当作"首次见到"放行，也不能当作"重复"丢弃：
                // 两种误判都会造成资损，交由上层按处理失败对待并让提供方重发。
                throw new IllegalStateException("回调幂等登记失败", failure);
            }
        };
    }

    // -----------------------------------------------------------------------
    // 第 4 步 · 写入提供方事件
    // -----------------------------------------------------------------------

    /**
     * 写入 {@code payment_provider_events}。
     *
     * <p>该表有 {@code CHECK (signature_verified)}——只有验签通过的事件才允许落库。
     * 管线保证到这一步时验签必然已通过，因此这里恒填 {@code true}；
     * 若将来有人把这个调用挪到验签之前，数据库会直接拒绝，这是有意的第二道防线。
     */
    public static PaymentCallbackPipeline.ProviderEventStore providerEventStore(
            DataSource source, String organizationId) {
        return (callback, rawBody) -> {
            String sql = """
                    INSERT INTO payment_provider_events (
                        payment_provider_event_id, organization_id, provider, event_type,
                        object_ref, amount_minor, currency, event_created_at,
                        payload_sha256, signature_verified, processing_status, idempotency_key)
                    VALUES (?, ?, ?, ?, ?, ?, 'CNY', now(), ?, true, 'APPLIED', ?)
                    """;
            try (Connection connection = source.getConnection();
                 PreparedStatement statement = connection.prepareStatement(sql)) {
                statement.setString(1, callback.providerEventId());
                statement.setString(2, organizationId);
                statement.setString(3, callback.provider().name());
                statement.setString(4, callback.tradeStatus());
                statement.setString(5, callback.outTradeNo());
                statement.setLong(6, callback.amountFen());
                statement.setString(7, sha256Hex(rawBody));
                statement.setString(8, PaymentCallbackPipeline.idempotencyKey(callback));
                statement.executeUpdate();
            } catch (SQLException failure) {
                throw new IllegalStateException("写入提供方事件失败", failure);
            }
        };
    }

    // -----------------------------------------------------------------------
    // 对账案件 / 无主回调
    // -----------------------------------------------------------------------

    /**
     * 按订单是否已知分流。
     *
     * <p>{@code payment_reconciliation_cases.organization_id} 是 NOT NULL，
     * 而 ORDER_UNKNOWN 恰恰是组织未知的那一支，写不进去。
     * 用哨兵组织填充会污染租户数据并破坏 RLS 语义，因此落到
     * {@code payment_unmatched_callbacks} 滞留表，由人工认领后转正式案件。
     */
    public static PaymentCallbackPipeline.ReconciliationCases reconciliationCases(
            DataSource source) {
        return (reasonCode, callback, order, detail) -> {
            if (order == null) {
                insertUnmatched(source, reasonCode, callback, detail);
            } else {
                insertCase(source, reasonCode, callback, order, detail);
            }
        };
    }

    private static void insertUnmatched(DataSource source, String reasonCode,
                                        PaymentCallbackPipeline.NormalizedCallback callback,
                                        String detail) {
        String sql = """
                INSERT INTO payment_unmatched_callbacks (
                    provider, provider_event_id, out_trade_no, amount_minor, reason_code, detail)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (provider, provider_event_id) DO NOTHING
                """;
        try (Connection connection = source.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, callback.provider().name());
            statement.setString(2, callback.providerEventId());
            statement.setString(3, callback.outTradeNo());
            statement.setLong(4, callback.amountFen());
            statement.setString(5, reasonCode);
            statement.setString(6, detail);
            statement.executeUpdate();
        } catch (SQLException failure) {
            throw new IllegalStateException("写入无主回调失败", failure);
        }
    }

    private static void insertCase(DataSource source, String reasonCode,
                                   PaymentCallbackPipeline.NormalizedCallback callback,
                                   PaymentCallbackPipeline.LocalOrder order, String detail) {
        String sql = """
                INSERT INTO payment_reconciliation_cases (
                    payment_reconciliation_case_id, organization_id, provider,
                    provider_object_ref, expected_state, observed_state,
                    status, reason_code, idempotency_key)
                VALUES (?, ?, ?, ?, ?, ?, 'OPEN', ?, ?)
                ON CONFLICT (organization_id, idempotency_key) DO NOTHING
                """;
        try (Connection connection = source.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            String caseId = "case-" + callback.provider().name().toLowerCase()
                    + "-" + callback.providerEventId();
            statement.setString(1, caseId);
            statement.setString(2, order.organizationId());
            statement.setString(3, callback.provider().name());
            statement.setString(4, callback.outTradeNo());
            statement.setString(5, "AMOUNT=" + order.expectedAmountFen());
            statement.setString(6, "AMOUNT=" + callback.amountFen());
            statement.setString(7, reasonCode);
            statement.setString(8, PaymentCallbackPipeline.idempotencyKey(callback));
            statement.executeUpdate();
        } catch (SQLException failure) {
            throw new IllegalStateException("开立对账案件失败", failure);
        }
    }

    // -----------------------------------------------------------------------

    /** 幂等键形如 {@code PROVIDER:eventId}，事件 ID 本身可能含冒号，只切第一个。 */
    static String[] splitKey(String idempotencyKey) {
        if (idempotencyKey == null) {
            throw new IllegalArgumentException("幂等键为空");
        }
        int separator = idempotencyKey.indexOf(':');
        if (separator <= 0 || separator == idempotencyKey.length() - 1) {
            throw new IllegalArgumentException("幂等键格式非法: " + idempotencyKey);
        }
        return new String[] {
                idempotencyKey.substring(0, separator),
                idempotencyKey.substring(separator + 1)
        };
    }

    static String sha256Hex(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(
                    digest.digest(value == null ? new byte[0]
                            : value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException("SHA-256 不可用", impossible);
        }
    }
}
