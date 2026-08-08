#!/usr/bin/env bash
# 订单目录（payment_order_directory）的真库验证。
#
# 回答一个具体问题：**回调路径现在真的能解析出组织了吗**，
# 同时确认租户隔离一点没被削弱。
#
# ---------------------------------------------------------------------------
# 两种模式
# ---------------------------------------------------------------------------
# 真实 schema 模式（目标库里已有 organizations 表 —— 即完整迁移链已应用）：
#     不删任何东西，直接在真实的 payment_checkout_sessions 上插测试行做断言。
#     CI 里就是这种情况：job 先按序应用 V1..V62，再跑本脚本。
#
# 夹具模式（空库）：
#     按 V49 原样重建 payment_checkout_sessions（含强制 RLS），
#     复现"直接查会返回 0 行"的故障，再应用迁移验证修复。
#     用于不想拉整条迁移链的本地快速验证。
#
# 早先本脚本无条件 DROP 再重建。那在 CI 里意味着：先applied 的真实 schema 被删掉，
# 脚本转而验证自己重建的一份副本 —— **测试通过了，但验的不是要验的东西**。
# 这与本脚本第一版用超级用户跑导致 RLS 故障复现不出来是同一类错误。
#
# 用法：DATABASE_URL=postgresql://... ./verify_order_directory.sh
#
# 退出码：0 全部通过 / 1 有断言失败 / 3 数据库不可达（NOT_RUN，不等于通过）

set -uo pipefail

DATABASE_URL="${DATABASE_URL:?DATABASE_URL 未设置}"
# 按文件名而不是版本号定位：迁移编号会变（本文件最初编号 V55，与既有迁移撞号后改为 V62），
# 把版本号写死等于让脚本随时可能指向一个不存在的文件。
MIGRATION="${MIGRATION:-$(ls modules/persistence/src/main/resources/db/migration/V*__payment_order_directory.sql 2>/dev/null | head -1)}"
HARDENING_MIGRATION="${HARDENING_MIGRATION:-$(ls modules/persistence/src/main/resources/db/migration/V*__payment_order_directory_trigger_security.sql 2>/dev/null | head -1)}"

pass=0
fail=0

if ! psql "$DATABASE_URL" -tAc 'SELECT 1' >/dev/null 2>&1; then
    echo "NOT_RUN: 数据库不可达。这不等于通过。"
    exit 3
fi

check() {
    if [ "$2" = "$3" ]; then
        pass=$((pass + 1))
        printf '  [PASS] %s\n' "$1"
    else
        fail=$((fail + 1))
        printf '  [FAIL] %s  期望=%s 实际=%s\n' "$1" "$3" "$2"
    fi
}

q() { psql "$DATABASE_URL" -tAc "$1" 2>/dev/null | tail -1 | tr -d ' '; }

# 以运行角色执行，可选带租户上下文。
# 这才是回调路径的真实身份：非属主、非超级用户、受 RLS 约束。
# 用超级用户跑会绕过 RLS，把要验的东西验没了 —— 本脚本第一版就是这么"通过"的。
as_runtime() {
    local prelude="SET ROLE elmos_billing_runtime;"
    [ -n "${2:-}" ] && prelude="$prelude SET app.organization_id = '$2';"
    psql "$DATABASE_URL" -tAc "$prelude $1" 2>/dev/null | tail -1 | tr -d ' '
}

exists() { [ "$(q "SELECT to_regclass('public.$1') IS NOT NULL")" = "t" ]; }

# ---------------------------------------------------------------------------

psql "$DATABASE_URL" -q >/dev/null 2>&1 <<'SQL'
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'elmos_billing_runtime') THEN
        CREATE ROLE elmos_billing_runtime NOLOGIN;
    END IF;
END
$$;
GRANT USAGE ON SCHEMA public TO elmos_billing_runtime;
SQL

if exists organizations; then
    MODE=real
    echo "== 模式：真实 schema（完整迁移链已应用） =="
else
    MODE=fixture
    echo "== 模式：夹具（空库，按 V49 原样重建） =="
fi

# ---------------------------------------------------------------------------

SUFFIX="vod$$"
ORG_A="org-$SUFFIX-a"
ORG_B="org-$SUFFIX-b"
ORD_A="checkout-$SUFFIX-a"
ORD_B="checkout-$SUFFIX-b"

if [ "$MODE" = fixture ]; then
    if [ ! -f "$MIGRATION" ] || [ ! -f "$HARDENING_MIGRATION" ]; then
        echo "NOT_RUN: 找不到订单目录或触发器加固迁移。请在仓库根目录运行，或设置 MIGRATION=/HARDENING_MIGRATION=。"
        exit 3
    fi
    psql "$DATABASE_URL" -q >/dev/null <<SQL
DROP TABLE IF EXISTS payment_order_directory CASCADE;
DROP TABLE IF EXISTS payment_checkout_sessions CASCADE;
DROP FUNCTION IF EXISTS elmos_sync_payment_order_directory() CASCADE;

CREATE TABLE payment_checkout_sessions (
    checkout_session_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL,
    actor_id varchar(96) NOT NULL,
    plan_id varchar(96) NOT NULL,
    amount_minor numeric(19,0) NOT NULL,
    status varchar(32) NOT NULL,
    idempotency_key varchar(160) NOT NULL,
    request_hash char(64) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- V49 第 419 行起的租户表清单对每张表做的三件事，原样照搬
ALTER TABLE payment_checkout_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE payment_checkout_sessions FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON payment_checkout_sessions
    USING (organization_id = current_setting('app.organization_id', true))
    WITH CHECK (organization_id = current_setting('app.organization_id', true));

GRANT SELECT, INSERT, UPDATE ON payment_checkout_sessions TO elmos_billing_runtime;

BEGIN;
SELECT set_config('app.organization_id', '$ORG_A', true);
INSERT INTO payment_checkout_sessions
    (checkout_session_id, organization_id, actor_id, plan_id, amount_minor, status,
     idempotency_key, request_hash)
VALUES ('$ORD_A', '$ORG_A', 'actor-a', 'elmos-pro-monthly', 12900, 'OPEN',
        'idem-$SUFFIX-a', repeat('a', 64));
COMMIT;
SQL

    echo
    echo "== 复现故障：无租户上下文时直接查订单表 =="
    # 这正是回调到达时的处境 —— 组织未知，设不了 app.organization_id
    visible=$(as_runtime "SELECT count(*) FROM payment_checkout_sessions WHERE checkout_session_id = '$ORD_A'")
    check "无上下文直查 payment_checkout_sessions 返回 0 行（原实现全判 ORDER_UNKNOWN 的原因）" "$visible" "0"

    echo
    echo "== 应用订单目录迁移 =="
    psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -f "$MIGRATION" >/dev/null
    psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -f "$HARDENING_MIGRATION" >/dev/null

    echo
    echo "== 回填 =="
    check "既有订单被回填" "$(q "SELECT count(*) FROM payment_order_directory WHERE checkout_session_id='$ORD_A'")" "1"
    check "回填出来的组织正确" "$(q "SELECT organization_id FROM payment_order_directory WHERE checkout_session_id='$ORD_A'")" "$ORG_A"
else
    # 真实 schema：迁移已经在链里应用过，目录表必须已经存在
    check "payment_order_directory 已由迁移链创建" "$(q "SELECT to_regclass('public.payment_order_directory') IS NOT NULL")" "t"
    psql "$DATABASE_URL" -q >/dev/null <<SQL
GRANT SELECT, INSERT, UPDATE ON payment_checkout_sessions TO elmos_billing_runtime;
GRANT SELECT ON payment_order_directory TO elmos_billing_runtime;
INSERT INTO organizations (organization_id) VALUES ('$ORG_A'), ('$ORG_B') ON CONFLICT DO NOTHING;

BEGIN;
SELECT set_config('app.organization_id', '$ORG_A', true);
INSERT INTO payment_checkout_sessions
    (checkout_session_id, organization_id, actor_id, plan_id, catalog_version, currency,
     amount_minor, provider, status, expires_at, idempotency_key, request_hash)
VALUES ('$ORD_A', '$ORG_A', 'actor-a', 'elmos-pro-monthly', '2026-07-28.2', 'CNY',
        12900, 'ALIPAY_CHECKOUT', 'OPEN', now() + interval '30 min',
        'idem-$SUFFIX-a', repeat('a', 64));
COMMIT;

BEGIN;
SELECT set_config('app.organization_id', '$ORG_B', true);
INSERT INTO payment_checkout_sessions
    (checkout_session_id, organization_id, actor_id, plan_id, catalog_version, currency,
     amount_minor, provider, status, expires_at, idempotency_key, request_hash)
VALUES ('$ORD_B', '$ORG_B', 'actor-b', 'elmos-pro-annual', '2026-07-28.2', 'CNY',
        129000, 'WECHAT_PAY_NATIVE', 'OPEN', now() + interval '30 min',
        'idem-$SUFFIX-b', repeat('b', 64));
COMMIT;
SQL
    echo
    echo "== 触发器在真实表上生效 =="
    check "org-B 的订单被同步进目录" "$(q "SELECT organization_id FROM payment_order_directory WHERE checkout_session_id='$ORD_B'")" "$ORG_B"
    check "金额一并同步" "$(q "SELECT amount_minor FROM payment_order_directory WHERE checkout_session_id='$ORD_B'")" "129000"
fi

# ---------------------------------------------------------------------------
# 以下断言两种模式都跑
# ---------------------------------------------------------------------------

echo
echo "== 触发器最小权限边界 =="
check "同步函数以 SECURITY DEFINER 执行" \
    "$(q "SELECT prosecdef FROM pg_proc WHERE oid='elmos_sync_payment_order_directory()'::regprocedure")" "t"
check "同步函数 search_path 固定且 pg_temp 最后" \
    "$(q "SELECT array_to_string(proconfig, ',') FROM pg_proc WHERE oid='elmos_sync_payment_order_directory()'::regprocedure")" \
    "search_path=pg_catalog,public,pg_temp"
check "运行角色不能直接执行同步函数" \
    "$(q "SELECT has_function_privilege('elmos_billing_runtime', 'elmos_sync_payment_order_directory()', 'EXECUTE')")" "f"

echo
echo "== 租户隔离没有被削弱 =="
check "payment_checkout_sessions 的 FORCE RLS 生效" \
    "$(q "SELECT relforcerowsecurity FROM pg_class WHERE relname='payment_checkout_sessions'")" "t"
check "payment_checkout_sessions 的 RLS 已启用" \
    "$(q "SELECT relrowsecurity FROM pg_class WHERE relname='payment_checkout_sessions'")" "t"
check "运行角色无上下文看不到任何订单行" \
    "$(as_runtime "SELECT count(*) FROM payment_checkout_sessions")" "0"
check "设了 org-A 上下文只看得到自己那 1 行" \
    "$(as_runtime "SELECT count(*) FROM payment_checkout_sessions WHERE checkout_session_id='$ORD_A'" "$ORG_A")" "1"
check "设了 org-A 上下文看不到 org-B 的订单" \
    "$(as_runtime "SELECT count(*) FROM payment_checkout_sessions WHERE checkout_session_id='$ORD_B'" "$ORG_A")" "0"

echo
echo "== 目录可在无上下文时读取（这正是它存在的理由） =="
check "无上下文也能解析出组织" \
    "$(as_runtime "SELECT organization_id FROM payment_order_directory WHERE checkout_session_id='$ORD_A'")" "$ORG_A"
check "目录表本身不加 RLS（有意为之）" \
    "$(q "SELECT relrowsecurity FROM pg_class WHERE relname='payment_order_directory'")" "f"

echo
echo "== 触发器：状态变更同步，业务字段不变 =="
psql "$DATABASE_URL" -q >/dev/null <<SQL
BEGIN;
SELECT set_config('app.organization_id', '$ORG_A', true);
UPDATE payment_checkout_sessions SET status = 'COMPLETED' WHERE checkout_session_id = '$ORD_A';
COMMIT;
SQL
check "状态变更同步到目录" "$(q "SELECT status FROM payment_order_directory WHERE checkout_session_id='$ORD_A'")" "COMPLETED"
check "同步是 UPSERT，不产生重复行" "$(q "SELECT count(*) FROM payment_order_directory WHERE checkout_session_id='$ORD_A'")" "1"

# 组织/套餐/金额刻意不随 UPDATE 变更：真变了说明上游出了问题，目录保留首次值以便对账发现
psql "$DATABASE_URL" -q >/dev/null <<SQL
BEGIN;
SELECT set_config('app.organization_id', '$ORG_A', true);
UPDATE payment_checkout_sessions SET amount_minor = 1, status = 'OPEN'
 WHERE checkout_session_id = '$ORD_A';
COMMIT;
SQL
check "金额被改动时目录保留首次值（供对账发现不一致）" \
    "$(q "SELECT amount_minor FROM payment_order_directory WHERE checkout_session_id='$ORD_A'")" "12900"

echo
echo "== 回调查询的完整形态 =="
check "JdbcOrderPorts.orderLookup 的那条 SQL 能查到组织" \
    "$(as_runtime "SELECT organization_id FROM payment_order_directory WHERE checkout_session_id='$ORD_A' AND status IN ('CREATING','OPEN','COMPLETED')")" "$ORG_A"

psql "$DATABASE_URL" -q >/dev/null <<SQL
BEGIN;
SELECT set_config('app.organization_id', '$ORG_A', true);
UPDATE payment_checkout_sessions SET status = 'EXPIRED' WHERE checkout_session_id = '$ORD_A';
COMMIT;
SQL
check "已过期订单被状态白名单挡在外面（应进对账）" \
    "$(as_runtime "SELECT count(*) FROM payment_order_directory WHERE checkout_session_id='$ORD_A' AND status IN ('CREATING','OPEN','COMPLETED')")" "0"

echo
echo "== 运行角色只能读目录，不能写 =="
# 目录与源表的一致性只能由触发器保证。应用代码即使想直接改也必须改不了。
denied=$(psql "$DATABASE_URL" -tAc "SET ROLE elmos_billing_runtime; INSERT INTO payment_order_directory (checkout_session_id, organization_id, plan_id, amount_minor, status) VALUES ('forged-$SUFFIX','org-evil','p',1,'OPEN');" 2>&1 | grep -c 'permission denied' || true)
check "运行角色直接 INSERT 目录被拒绝" "$denied" "1"
check "伪造行确实没有落库" "$(q "SELECT count(*) FROM payment_order_directory WHERE checkout_session_id='forged-$SUFFIX'")" "0"

echo
echo "模式=${MODE}，结果：${pass} 通过，${fail} 失败"
[ "$fail" -eq 0 ] || exit 1
