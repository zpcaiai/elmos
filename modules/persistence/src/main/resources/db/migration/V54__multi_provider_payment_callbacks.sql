-- V54 · 多支付通道与回调幂等
--
-- 触发：D-01（2026-07-28）选定中国大陆主体 + 支付宝/微信支付。
--
-- V49 把两张支付表的 provider 列写死为 CHECK (provider = 'STRIPE_CHECKOUT')。
-- 不放开这两个约束，写入支付宝/微信记录会在运行期被约束挡掉 ——
-- 症状是回调处理到第 4 步才失败，此时提供方已经扣款，订单进入挂账。
--
-- 版本号说明：现有迁移为 V49、V50、V51、V53（V52 是空缺号）。
-- 本迁移取 V54 而不是填补 V52：Flyway 默认禁止乱序，
-- 在 V53 已应用的库上插入 V52 会直接失败。空缺号保持空缺。
--
-- 前向迁移：不修改任何既有行，不删除任何列。

-- ---------------------------------------------------------------------------
-- 1. 放开 provider 取值域
-- ---------------------------------------------------------------------------
-- 取值域必须与以下三处保持一致，任一处漂移都会造成运行期失败：
--   contracts/pricing-catalog-schema/elmos-pricing-catalog.schema.json
--   apps/commercial-api/.../payment/PaymentProvider.java
--   apps/web-console/app/lib/pricingCatalog.ts

ALTER TABLE payment_checkout_sessions
    DROP CONSTRAINT IF EXISTS payment_checkout_sessions_provider_check;
ALTER TABLE payment_checkout_sessions
    ADD CONSTRAINT payment_checkout_sessions_provider_check
    CHECK (provider IN ('STRIPE_CHECKOUT', 'ALIPAY_CHECKOUT', 'WECHAT_PAY_NATIVE'));

ALTER TABLE payment_provider_events
    DROP CONSTRAINT IF EXISTS payment_provider_events_provider_check;
ALTER TABLE payment_provider_events
    ADD CONSTRAINT payment_provider_events_provider_check
    CHECK (provider IN ('STRIPE_CHECKOUT', 'ALIPAY_CHECKOUT', 'WECHAT_PAY_NATIVE'));

-- ---------------------------------------------------------------------------
-- 2. 回调幂等台账
-- ---------------------------------------------------------------------------
-- 为什么不复用 payment_provider_events 的 UNIQUE (organization_id, idempotency_key)：
--
--   那个唯一约束按组织分区，但**回调到达时组织还未知** —— 组织要靠
--   out_trade_no 查订单才能确定，而查订单发生在幂等去重之后（第 3 步）。
--   若把幂等推迟到组织已知之后，重复回调会先做完查单，
--   在并发重发下两个请求可能同时通过查单再同时写事件。
--
--   因此这里用一张**不分租户**的全局台账，在任何业务动作之前登记。
--   它只存通道、提供方事件 ID 和接收时间，不存金额、订单号、
--   组织或任何回调载荷 —— 没有租户数据，也就没有跨租户泄露面，
--   所以不加 RLS（这是有意的例外，不是遗漏）。
--
-- 幂等键是 (provider, provider_event_id)：
--   不能用 out_trade_no —— 同一订单会有支付成功、退款、关单多个事件，
--   用订单号做键会把后续事件全部误判为重复并静默丢弃。

CREATE TABLE payment_callback_receipts (
    provider varchar(32) NOT NULL CHECK (
        provider IN ('STRIPE_CHECKOUT', 'ALIPAY_CHECKOUT', 'WECHAT_PAY_NATIVE')
    ),
    provider_event_id varchar(255) NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (provider, provider_event_id)
);

COMMENT ON TABLE payment_callback_receipts IS
    '回调幂等台账。登记发生在验签之后、任何副作用之前。'
    '主键即幂等键；重复回调靠主键冲突拒绝，不得用先查后插实现。';

-- 保留期清理用（回调重发窗口远小于 90 天，超期记录可安全归档）
CREATE INDEX payment_callback_receipts_received_at_idx
    ON payment_callback_receipts (received_at);

-- ---------------------------------------------------------------------------
-- 3. 无主回调滞留表
-- ---------------------------------------------------------------------------
-- payment_reconciliation_cases.organization_id 是 NOT NULL，
-- 但回调管线的 ORDER_UNKNOWN 分支**恰恰是组织未知**的那一支：
-- 组织要靠 out_trade_no 查订单才能确定，查不到就没有组织可填。
--
-- 用哨兵组织填充会污染租户数据并破坏 RLS 语义；丢弃则违反"原始事实不丢"。
-- 因此单列一张不含租户列的滞留表，由人工在对账时认领并转入正式案件。
--
-- 与 payment_callback_receipts 同理：不含租户数据，因此不加 RLS。
-- 但它会存 out_trade_no 与金额（对账必需），所以只授予运维角色读取。

CREATE TABLE payment_unmatched_callbacks (
    payment_unmatched_callback_id bigserial PRIMARY KEY,
    provider varchar(32) NOT NULL CHECK (
        provider IN ('STRIPE_CHECKOUT', 'ALIPAY_CHECKOUT', 'WECHAT_PAY_NATIVE')
    ),
    provider_event_id varchar(255) NOT NULL,
    out_trade_no varchar(255) NOT NULL,
    amount_minor numeric(19,0) NOT NULL,
    reason_code varchar(96) NOT NULL CHECK (reason_code IN ('ORDER_UNKNOWN')),
    detail text NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    claimed_at timestamptz,
    claimed_case_id varchar(96),
    UNIQUE (provider, provider_event_id),
    CHECK ((claimed_at IS NULL AND claimed_case_id IS NULL)
        OR (claimed_at IS NOT NULL AND claimed_case_id IS NOT NULL))
);

COMMENT ON TABLE payment_unmatched_callbacks IS
    '验签通过但在本地找不到对应订单的回调。组织未知，因此不能写入 '
    'payment_reconciliation_cases（其 organization_id 为 NOT NULL）。'
    '人工认领后再转入正式对账案件。';

CREATE INDEX payment_unmatched_callbacks_open_idx
    ON payment_unmatched_callbacks (received_at) WHERE claimed_at IS NULL;

-- ---------------------------------------------------------------------------
-- 4. 运行角色权限
-- ---------------------------------------------------------------------------
-- 台账只允许插入与查询：回调处理不需要 UPDATE 或 DELETE，
-- 不授予就能杜绝"把已处理事件改回未处理"这类绕过幂等的操作。
-- 清理由独立的运维角色执行。

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'elmos_billing_runtime') THEN
        EXECUTE 'GRANT SELECT, INSERT ON payment_callback_receipts TO elmos_billing_runtime';
        EXECUTE 'GRANT SELECT, INSERT ON payment_unmatched_callbacks TO elmos_billing_runtime';
        EXECUTE 'GRANT USAGE ON SEQUENCE payment_unmatched_callbacks_payment_unmatched_callback_id_seq '
                'TO elmos_billing_runtime';
    END IF;
END
$$;
