-- V62 · 回调订单目录（跨租户解析的最小信任面）
--
-- 触发：V54 之后接线 JdbcOrderPorts 时发现，回调链路上有两处在真库里跑不通。
--
-- 版本号说明：本文件最初编号为 V55，与既有的
-- V55__account_identity_and_organization_self_service.sql 撞号，
-- Flyway 直接拒绝启动（"Found more than one migration with version 55"）。
-- 撞号的原因是选号时依据了一份过期的迁移清单而没有重新列目录 ——
-- 仓库当时已经到 V61。改为 V62。
--
-- 教训写在这里而不是删掉：选迁移版本号必须现场 `ls` 一次，
-- 上一次的记忆不算数。
--
-- ---------------------------------------------------------------------------
-- 问题
-- ---------------------------------------------------------------------------
-- V49 第 419 行起的租户表清单里包含 payment_checkout_sessions：
--
--     ALTER TABLE payment_checkout_sessions ENABLE  ROW LEVEL SECURITY;
--     ALTER TABLE payment_checkout_sessions FORCE   ROW LEVEL SECURITY;
--     CREATE POLICY tenant_isolation ON payment_checkout_sessions
--         USING (organization_id = current_setting('app.organization_id', true));
--
-- 支付回调到达时**组织是未知的** —— 组织正是要靠 out_trade_no 查订单才能确定。
-- 于是设不了 app.organization_id，策略求值成 organization_id = NULL，
-- 恒为 NULL，SELECT 一行都不返回。
--
-- 后果不是报错，是**静默全错**：每一笔回调都判成 ORDER_UNKNOWN，
-- 全部落进 payment_unmatched_callbacks，一个订阅都不会开通，
-- 而提供方会持续重发直到有人去翻滞留表。
--
-- ---------------------------------------------------------------------------
-- 为什么不用其它办法
-- ---------------------------------------------------------------------------
-- BYPASSRLS 角色：等于对整张 payment_checkout_sessions 关掉租户隔离，
--   而那张表带 actor_id、idempotency_key、request_hash 等敏感列。
--   为了解析一个组织 ID 而敞开整张表，代价不成比例。
--
-- SECURITY DEFINER 函数：FORCE ROW LEVEL SECURITY 对表属主同样生效，
--   函数属主也逃不掉，除非属主带 BYPASSRLS —— 绕回上一条。
--
-- 放宽策略为 "app.organization_id 未设置时全放行"：这是最危险的一种，
--   任何忘记设上下文的代码路径都会静默变成跨租户可读。
--
-- ---------------------------------------------------------------------------
-- 本迁移的做法
-- ---------------------------------------------------------------------------
-- 单列一张**只含解析所必需的最小列**的目录表，不加 RLS，由触发器自动维护。
-- 跨租户可读的信息因此被压缩成一个明确、可审计的集合：
--
--     订单号 → (组织, 套餐, 金额, 状态)
--
-- 没有 actor_id，没有幂等键，没有请求哈希，没有时间戳以外的任何审计字段。
-- 知道一个订单号的人只能问出"这单属于哪个组织、哪个套餐、多少钱"——
-- 而订单号本来就是我们发给支付提供方、再由提供方回传的东西。
--
-- 与 payment_callback_receipts / payment_unmatched_callbacks 一样，
-- 「不加 RLS」是有意的设计决定，不是遗漏，理由写在这里备查。
--
-- 前向迁移：不修改任何既有行，不删除任何列，不改变既有表的 RLS 配置。

-- ---------------------------------------------------------------------------
-- 1. 目录表
-- ---------------------------------------------------------------------------

CREATE TABLE payment_order_directory (
    checkout_session_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL,
    plan_id varchar(96) NOT NULL,
    amount_minor numeric(19,0) NOT NULL CHECK (amount_minor >= 0),
    status varchar(32) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE payment_order_directory IS
    '支付回调的订单→组织解析目录。payment_checkout_sessions 启用了强制 RLS，'
    '而回调到达时组织未知、设不了 app.organization_id，因此无法直接查询。'
    '本表只含解析所需的最小列，不加 RLS（有意为之，理由见 V62 迁移注释）。';

COMMENT ON COLUMN payment_order_directory.status IS
    '镜像自 payment_checkout_sessions.status。回调只接受 '
    'CREATING/OPEN/COMPLETED；EXPIRED/FAILED 上的支付成功回调应进对账。';

CREATE INDEX payment_order_directory_organization_idx
    ON payment_order_directory (organization_id);

-- ---------------------------------------------------------------------------
-- 2. 自动维护
-- ---------------------------------------------------------------------------
-- 用触发器而不是在应用代码里双写：双写总有人会忘，
-- 而忘记的后果（该组织的回调全部变成无主）只在生产收到真实回调时才暴露。
--
-- 触发器函数不是 SECURITY DEFINER：它写的是无 RLS 的目录表，
-- 调用者的普通权限就够，不需要提权。

CREATE OR REPLACE FUNCTION elmos_sync_payment_order_directory()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO payment_order_directory (
        checkout_session_id, organization_id, plan_id, amount_minor, status)
    VALUES (
        NEW.checkout_session_id, NEW.organization_id, NEW.plan_id,
        NEW.amount_minor, NEW.status)
    ON CONFLICT (checkout_session_id) DO UPDATE
        SET status = EXCLUDED.status,
            updated_at = now();
    -- 组织、套餐、金额刻意**不**在 DO UPDATE 里更新：
    -- 这三者一旦确定就不该变，若源表发生了变更，说明有更严重的问题，
    -- 目录保留首次写入的值，让对账时能看出两边不一致。
    RETURN NEW;
END;
$$;

CREATE TRIGGER payment_checkout_sessions_directory_sync
AFTER INSERT OR UPDATE OF status ON payment_checkout_sessions
FOR EACH ROW EXECUTE FUNCTION elmos_sync_payment_order_directory();

-- ---------------------------------------------------------------------------
-- 3. 回填既有订单
-- ---------------------------------------------------------------------------
-- 触发器只对将来的行生效。已存在的订单必须回填，否则它们的回调仍会变成无主。
--
-- 回填必须能看见**全部**既有行，而 payment_checkout_sessions 是 FORCE RLS：
-- FORCE 的含义正是"连表属主也受策略约束"，所以属主直接 SELECT 同样只看得到
-- app.organization_id 匹配的行（在迁移上下文里是 0 行）。
--
-- 两个常见做法在这里都不合适：
--   SET row_security = off —— 在 FORCE RLS 表上会直接报错，除非角色带 BYPASSRLS；
--   给迁移角色加 BYPASSRLS —— 为一次回填授予一个永久的、全库范围的特权。
--
-- 因此改为在同一事务内临时摘掉 FORCE、回填、立刻装回。
-- 关键点：这三步在 Flyway 的同一个事务里，任何一步失败都会整体回滚，
-- 不存在"FORCE 被摘掉但没装回来"的中间状态。
-- 摘掉 FORCE 期间策略对非属主依然生效，敞开的只是属主自己这一条路径。

ALTER TABLE payment_checkout_sessions NO FORCE ROW LEVEL SECURITY;

DO $$
DECLARE
    source_rows bigint;
    copied_rows bigint;
BEGIN
    SELECT count(*) INTO source_rows FROM payment_checkout_sessions;

    INSERT INTO payment_order_directory (
        checkout_session_id, organization_id, plan_id, amount_minor, status)
    SELECT checkout_session_id, organization_id, plan_id, amount_minor, status
      FROM payment_checkout_sessions
    ON CONFLICT (checkout_session_id) DO NOTHING;

    GET DIAGNOSTICS copied_rows = ROW_COUNT;

    -- 断言而不是记日志：静默的空回填正是本迁移要修的那一类故障，
    -- 让它以同样的方式再发生一次是说不过去的。
    IF copied_rows <> source_rows THEN
        RAISE EXCEPTION
            '订单目录回填不完整：源表可见 % 行，实际写入 % 行。'
            '两者必须相等（目录此前为空）。请检查执行本迁移的角色是否为 '
            'payment_checkout_sessions 的属主。',
            source_rows, copied_rows;
    END IF;

    RAISE NOTICE '订单目录回填完成：% 行', copied_rows;
END
$$;

-- 立刻装回。与上面的 NO FORCE 在同一事务内，缺一不可。
ALTER TABLE payment_checkout_sessions FORCE ROW LEVEL SECURITY;

-- 装回来了才算数：如果上一行被人删掉或改错，这个断言会让迁移失败，
-- 而不是留下一张对属主敞开的租户表。
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_class
         WHERE relname = 'payment_checkout_sessions'
           AND relrowsecurity
           AND relforcerowsecurity
    ) THEN
        RAISE EXCEPTION
            'payment_checkout_sessions 的 FORCE ROW LEVEL SECURITY 未恢复，拒绝提交本迁移';
    END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- 4. 运行角色权限
-- ---------------------------------------------------------------------------
-- 回调路径只读目录，写入全部由触发器完成，因此不授予 INSERT/UPDATE：
-- 应用代码即使想直接改目录也改不了，目录与源表的一致性只能由触发器保证。

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'elmos_billing_runtime') THEN
        EXECUTE 'GRANT SELECT ON payment_order_directory TO elmos_billing_runtime';
    END IF;
END
$$;
