package io.elmos.commercialadapter.payment;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Clock;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Optional;
import javax.sql.DataSource;

/**
 * 回调管线剩余两个端口的 PostgreSQL 实现。
 *
 * <p>这两个端口没有和 {@link JdbcCallbackPorts} 放在一起，是因为它们触碰的是
 * <b>业务状态</b>而不是回调台账：一个读订单，一个改订阅。两者都必须在
 * 租户上下文里执行，语义比前三个端口重得多。
 *
 * <h2>订单落在哪张表</h2>
 *
 * <p>{@code payment_checkout_sessions} 就是订单表：它带 {@code plan_id}、
 * {@code amount_minor}、{@code catalog_version} 和状态机。
 *
 * <p>{@code out_trade_no} 映射到 {@code checkout_session_id} 而不是
 * {@code provider_session_ref}。Stripe 路径按 {@code provider_session_ref} 查，
 * 是因为 Stripe 的会话 ID 由 Stripe 生成；而支付宝/微信的 {@code out_trade_no}
 * <b>由我们生成并传给提供方</b>，所以本地主键才是正确的查找键。
 *
 * <h2>订阅激活为什么不写裸 SQL</h2>
 *
 * <p>激活走存储函数 {@code elmos_activate_subscription_period}，与既有 Stripe
 * 路径完全一致。该函数在一次调用里同时写 {@code subscriptions}、
 * {@code quota_allocations}、{@code subscription_events} 并处理试用转付费，
 * 且每一处都带 ON CONFLICT 幂等。绕过它自己拼 INSERT 会漏掉额度发放，
 * 表现为"订阅显示已开通但用不了"。
 *
 * <p><b>该函数依赖会话级租户上下文</b>：内部用 {@code elmos_current_organization_id()}
 * 取组织。因此调用前必须 {@code SET LOCAL app.organization_id}，
 * 且必须与更新订单在同一个事务里 —— {@code SET LOCAL} 出了事务就失效。
 */
public final class JdbcOrderPorts {

    /** 套餐期限天数。由调用方从定价目录提供，本类不解析目录。 */
    public interface PlanTermDays {
        int termDays(String planId);
    }

    private JdbcOrderPorts() {
    }

    // -----------------------------------------------------------------------
    // 第 3 步 · 订单查询
    // -----------------------------------------------------------------------

    /**
     * 按 {@code out_trade_no}（即本地 {@code checkout_session_id}）查订单。
     *
     * <p>状态白名单包含 {@code COMPLETED}：回调重发时订单可能已经完成，
     * 此时仍应查得到并让管线走到幂等判定，而不是在这里变成 ORDER_UNKNOWN
     * —— 后者会把一笔正常的重发误判成无主回调，凭空制造对账工单。
     *
     * <p>不包含 {@code EXPIRED} / {@code FAILED}：那些订单上的支付成功回调
     * 确实是异常，应当进对账。
     *
     * <h2>为什么不直接查 payment_checkout_sessions（2026-07-29 修）</h2>
     *
     * <p>因为查不到。V49 把 {@code payment_checkout_sessions} 列进了强制 RLS 表清单
     * （{@code FORCE ROW LEVEL SECURITY}，策略
     * {@code organization_id = current_setting('app.organization_id', true)}）。
     * 回调到达时组织未知，设不了这个上下文，策略于是求值成
     * {@code organization_id = NULL} —— 恒为 NULL，一行都不返回。
     *
     * <p>原实现的注释里写着"若该表启用了强制 RLS，本查询必须以专用角色执行"，
     * 而它<b>确实</b>已经启用了。那条路径在真库上的结果是：
     * <b>每一笔回调都判成 ORDER_UNKNOWN</b>，全部进滞留表，没有一个订阅会被开通。
     * 而且这个故障是静默的——回调返回 400，提供方持续重发，
     * 直到有人去看 {@code payment_unmatched_callbacks} 才会发现。
     *
     * <p>解决办法不是给运行角色开 {@code BYPASSRLS}（那等于对整张表关掉租户隔离），
     * 而是 V62 引入的 {@code payment_order_directory}：一张<b>只含解析所需最小列</b>
     * 的无 RLS 目录表，由 {@code payment_checkout_sessions} 上的触发器自动维护。
     * 回调先用它把组织解析出来，此后所有读写都在正常租户上下文里进行。
     * 信任边界因此是显式且可审计的：能跨租户读到的只有
     * (订单号 → 组织, 套餐, 金额, 状态) 这一个映射，别的什么都没有。
     */
    public static PaymentCallbackPipeline.OrderLookup orderLookup(DataSource source) {
        return outTradeNo -> {
            String sql = """
                    SELECT checkout_session_id, organization_id, plan_id, amount_minor
                      FROM payment_order_directory
                     WHERE checkout_session_id = ?
                       AND status IN ('CREATING', 'OPEN', 'COMPLETED')
                    """;
            try (Connection connection = source.getConnection();
                 PreparedStatement statement = connection.prepareStatement(sql)) {
                statement.setString(1, outTradeNo);
                try (ResultSet rows = statement.executeQuery()) {
                    if (!rows.next()) {
                        return Optional.empty();
                    }
                    return Optional.of(new PaymentCallbackPipeline.LocalOrder(
                            rows.getString("checkout_session_id"),
                            rows.getString("organization_id"),
                            rows.getString("plan_id"),
                            rows.getLong("amount_minor")));
                }
            } catch (SQLException failure) {
                // 查不到订单与"查询本身失败"必须区分：前者进对账，后者应让提供方重发。
                throw new IllegalStateException("订单查询失败", failure);
            }
        };
    }

    // -----------------------------------------------------------------------
    // 第 5 步 · 订阅激活
    // -----------------------------------------------------------------------

    /**
     * 在<b>一个事务</b>里完成：设租户上下文 → 关单 → 激活订阅期。
     *
     * <p>与 Stripe 路径的差异：Stripe 把"会话完成"和"发票已付"拆成两个事件，
     * 分别关单和激活；支付宝/微信只有一个支付成功回调，两件事必须一起做。
     * 拆开做会出现"订单已关但额度没发"的中间态。
     *
     * @param actorId 记入订阅事件的操作者。回调没有交互式用户，
     *                应传一个专用的系统 Actor，不要复用客户身份。
     */
    public static PaymentCallbackPipeline.SubscriptionActivator subscriptionActivator(
            DataSource source, Clock clock, PlanTermDays planTerms, String actorId) {
        return (order, callback) -> {
            int termDays = planTerms.termDays(order.planId());
            if (termDays <= 0) {
                throw new IllegalStateException("套餐期限非法: " + order.planId());
            }
            Instant periodStart = clock.instant();
            Instant periodEnd = periodStart.plus(termDays, ChronoUnit.DAYS);

            // 订阅 ID 按「组织 + 套餐」确定性生成：手动续费时同一订阅被续期，
            // 而不是每次支付新建一条。函数内 ON CONFLICT (subscription_id) DO UPDATE
            // 会把期间往后推。
            String subscriptionId = deterministicId("sub", order.organizationId() + "|" + order.planId());
            // 额度分配按期间区分；函数内 ON CONFLICT (subscription_id, period_start) DO NOTHING
            String allocationId = deterministicId("qa", subscriptionId + "|" + periodStart.getEpochSecond());
            // 支付宝/微信没有"订阅对象"，用本地订单号合成一个稳定引用，
            // 满足 subscriptions(provider, provider_subscription_ref) 唯一索引。
            String providerSubscriptionRef = callback.provider().name().toLowerCase()
                    + ":" + order.orderId();

            try (Connection connection = source.getConnection()) {
                boolean previousAutoCommit = connection.getAutoCommit();
                connection.setAutoCommit(false);
                try {
                    // SET LOCAL 只在事务内有效，因此必须与后续语句同事务。
                    try (PreparedStatement tenant = connection.prepareStatement(
                            "SELECT set_config('app.organization_id', ?, true)")) {
                        tenant.setString(1, order.organizationId());
                        tenant.execute();
                    }

                    String closeOrder = """
                            UPDATE payment_checkout_sessions
                               SET status = 'COMPLETED',
                                   provider_session_ref = COALESCE(provider_session_ref, ?),
                                   completed_at = COALESCE(completed_at, now()),
                                   updated_at = now()
                             WHERE checkout_session_id = ?
                               AND organization_id = ?
                               AND status IN ('CREATING', 'OPEN', 'COMPLETED')
                            """;
                    int changed;
                    try (PreparedStatement statement = connection.prepareStatement(closeOrder)) {
                        statement.setString(1, callback.providerEventId());
                        statement.setString(2, order.orderId());
                        statement.setString(3, order.organizationId());
                        changed = statement.executeUpdate();
                    }
                    if (changed != 1) {
                        // 订单不在可关闭状态（已过期/已失败），不得继续激活订阅。
                        throw new IllegalStateException(
                                "订单状态不允许关闭: " + order.orderId());
                    }

                    String activate = """
                            SELECT elmos_activate_subscription_period(
                                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """;
                    try (PreparedStatement statement = connection.prepareStatement(activate)) {
                        statement.setString(1, subscriptionId);
                        statement.setString(2, allocationId);
                        statement.setString(3, actorId);
                        statement.setString(4, order.planId());
                        statement.setString(5, callback.provider().name());
                        statement.setString(6, order.organizationId());   // 无独立客户对象，用组织
                        statement.setString(7, providerSubscriptionRef);
                        statement.setObject(8, periodStart.atOffset(java.time.ZoneOffset.UTC));
                        statement.setObject(9, periodEnd.atOffset(java.time.ZoneOffset.UTC));
                        statement.setString(10, callback.providerEventId());
                        statement.setString(11, PaymentCallbackPipeline.idempotencyKey(callback));
                        statement.execute();
                    }
                    connection.commit();
                } catch (SQLException | RuntimeException failure) {
                    connection.rollback();
                    throw new IllegalStateException("订阅激活失败，已回滚", failure);
                } finally {
                    connection.setAutoCommit(previousAutoCommit);
                }
            } catch (SQLException failure) {
                throw new IllegalStateException("订阅激活连接失败", failure);
            }
        };
    }

    /** 确定性短 ID：同样的输入永远得到同样的 ID，保证续费幂等。 */
    static String deterministicId(String prefix, String seed) {
        return prefix + "-" + JdbcCallbackPorts.sha256Hex(seed).substring(0, 32);
    }
}
