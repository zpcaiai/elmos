#!/usr/bin/env bash
# V54 支付回调迁移的可复算验证
#
# 只在**可销毁**的 PostgreSQL 上运行。脚本会建库、建最小前置表、应用 V54，
# 然后逐条断言行为。任一断言不通过即以非零码退出。
#
# 用法：
#   ELMOS_PAYMENT_VERIFY_DSN="-h 127.0.0.1 -p 5432 -U postgres" \
#   ELMOS_PAYMENT_VERIFY_DISPOSABLE_CONFIRMED=true \
#     bash tooling/payment-db-verify/verify_payment_callbacks.sh
#
# 断言覆盖（全部是"错了会造成资损"的点）：
#   1. 迁移前写入非 Stripe 通道被 CHECK 挡掉（复现问题本身）
#   2. 迁移后三个通道均可写入，未知通道仍被拒
#   3. 并发争抢同一幂等键时**恰好一个**赢得登记
#   4. "先查后插"实现下两个会话都会看到 0 行（说明为何不能那样写）
#   5. 无主回调可落滞留表（组织未知时 payment_reconciliation_cases 写不进去）
#   6. 运行角色只有 SELECT/INSERT，没有 UPDATE/DELETE
#   7. 订单查询白名单与关单幂等（COMPLETED 可重入、EXPIRED 被拒、completed_at 不被覆盖）
set -Eeuo pipefail

DSN="${ELMOS_PAYMENT_VERIFY_DSN:-}"
[[ -n "$DSN" ]] || { echo "REFUSED: 未设置 ELMOS_PAYMENT_VERIFY_DSN" >&2; exit 2; }
[[ "${ELMOS_PAYMENT_VERIFY_DISPOSABLE_CONFIRMED:-}" == "true" ]] || {
  echo "REFUSED: 需显式设置 ELMOS_PAYMENT_VERIFY_DISPOSABLE_CONFIRMED=true" >&2; exit 2; }

MIGRATION="${ELMOS_PAYMENT_VERIFY_MIGRATION:-modules/persistence/src/main/resources/db/migration/V54__multi_provider_payment_callbacks.sql}"
[[ -f "$MIGRATION" ]] || { echo "REFUSED: 找不到迁移文件 $MIGRATION" >&2; exit 2; }

DB="elmos_payment_verify_$$"
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf '  [PASS] %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  [FAIL] %s\n' "$1"; }
# 注意：不要写成 `q "..." | grep -q ...`。
# 本脚本开启了 pipefail，psql 以非零码退出时整条管线就是非零，
# 即使 grep 命中也会被判成失败 —— 负向断言会全部误报。
# 一律先把输出存进变量再匹配。
q()    { psql $DSN -d "$DB" -tA -c "$1" 2>&1 || true; }
matches() { [[ "$1" == *"$2"* ]]; }

cleanup() { psql $DSN -q -c "DROP DATABASE IF EXISTS $DB;" >/dev/null 2>&1 || true; }
trap cleanup EXIT

psql $DSN -q -c "CREATE DATABASE $DB;"
psql $DSN -d "$DB" -q <<'SQL'
CREATE TABLE organizations (organization_id varchar(96) PRIMARY KEY);
CREATE TABLE payment_checkout_sessions (
    checkout_session_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    provider varchar(32) NOT NULL CHECK (provider = 'STRIPE_CHECKOUT'),
    amount_minor numeric(19,0) NOT NULL CHECK (amount_minor > 0),
    idempotency_key varchar(160) NOT NULL,
    UNIQUE (organization_id, idempotency_key));
CREATE TABLE payment_provider_events (
    payment_provider_event_id varchar(255) NOT NULL,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    provider varchar(32) NOT NULL CHECK (provider = 'STRIPE_CHECKOUT'),
    event_type varchar(64) NOT NULL, object_ref varchar(255) NOT NULL,
    payload_sha256 char(64) NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    signature_verified boolean NOT NULL CHECK (signature_verified),
    processing_status varchar(32) NOT NULL, idempotency_key varchar(160) NOT NULL,
    PRIMARY KEY (provider, payment_provider_event_id),
    UNIQUE (organization_id, idempotency_key));
INSERT INTO organizations VALUES ('org-1');
SQL

echo "1. 迁移前：非 Stripe 通道应被拒"
out=$(q "INSERT INTO payment_checkout_sessions VALUES ('cs-0','org-1','ALIPAY_CHECKOUT',12900,'k0');")
if matches "$out" "violates check constraint"; then
  ok "迁移前写入 ALIPAY_CHECKOUT 被 CHECK 挡掉（问题已复现）"
else
  bad "迁移前竟然允许 ALIPAY_CHECKOUT —— 前置表与 V49 定义不一致"
fi

echo "2. 应用 V54"
psql $DSN -d "$DB" -v ON_ERROR_STOP=1 -q -f "$MIGRATION" && ok "V54 应用成功" || bad "V54 应用失败"

echo "3. 迁移后：三个通道可写入，未知通道仍被拒"
n=0
for p in STRIPE_CHECKOUT ALIPAY_CHECKOUT WECHAT_PAY_NATIVE; do
  n=$((n+1))
  out=$(q "INSERT INTO payment_checkout_sessions VALUES ('cs-$n','org-1','$p',12900,'k$n');")
  matches "$out" "INSERT 0 1" && ok "$p 可写入" || bad "$p 写入失败"
done
out=$(q "INSERT INTO payment_checkout_sessions VALUES ('cs-x','org-1','PAYPAL',12900,'kx');")
matches "$out" "violates check constraint" && ok "未知通道 PAYPAL 仍被拒" || bad "未知通道未被拒"

echo "4. 并发幂等：20 个会话争同一个键"
q "TRUNCATE payment_callback_receipts;" >/dev/null
for _ in $(seq 1 20); do
  psql $DSN -d "$DB" -tA -c "INSERT INTO payment_callback_receipts (provider, provider_event_id)
      VALUES ('ALIPAY_CHECKOUT','evt-race')
      ON CONFLICT (provider, provider_event_id) DO NOTHING RETURNING 'WON';" &
done > /tmp/race.$$ 2>&1
wait
winners=$(grep -c WON /tmp/race.$$ || true)
rows=$(q "SELECT count(*) FROM payment_callback_receipts WHERE provider_event_id='evt-race';")
rm -f /tmp/race.$$
[[ "$winners" == "1" ]] && ok "恰好 1 个会话赢得登记（实测 $winners）" \
                        || bad "赢得登记的会话数为 $winners，应为 1"
[[ "$rows" == "1" ]] && ok "台账只有 1 行" || bad "台账行数为 $rows"

echo "5. 反例：先查后插的两个会话都会看到 0 行"
naive() {
  psql $DSN -d "$DB" -tA 2>&1 <<SQL
BEGIN;
SELECT 'seen=' || count(*) FROM payment_callback_receipts
  WHERE provider='ALIPAY_CHECKOUT' AND provider_event_id='evt-naive';
SELECT pg_sleep(0.5);
INSERT INTO payment_callback_receipts (provider, provider_event_id)
  VALUES ('ALIPAY_CHECKOUT','evt-naive');
COMMIT;
SQL
}
naive > /tmp/n1.$$ 2>&1 & sleep 0.1; naive > /tmp/n2.$$ 2>&1 & wait
zero=$(cat /tmp/n1.$$ /tmp/n2.$$ | grep -c "seen=0" || true)
rm -f /tmp/n1.$$ /tmp/n2.$$
[[ "$zero" == "2" ]] && ok "两个会话都看到 0 行 —— 先查后插会双双判定「首次见到」" \
                     || bad "预期两个 seen=0，实测 $zero"

echo "6. 无主回调滞留表"
out=$(q "INSERT INTO payment_unmatched_callbacks (provider, provider_event_id, out_trade_no,
    amount_minor, reason_code, detail)
   VALUES ('ALIPAY_CHECKOUT','evt-orphan','unknown-order',12900,'ORDER_UNKNOWN','本地无此订单');")
matches "$out" "INSERT 0 1" && ok "组织未知的回调可落滞留表" || bad "滞留表写入失败"
out=$(q "INSERT INTO payment_unmatched_callbacks (provider, provider_event_id, out_trade_no,
    amount_minor, reason_code, detail)
   VALUES ('ALIPAY_CHECKOUT','evt-orphan2','o',1,'AMOUNT_MISMATCH','x');")
matches "$out" "violates check constraint" \
  && ok "滞留表只接受 ORDER_UNKNOWN（金额不符有组织，应进正式案件）" \
  || bad "滞留表未限制 reason_code"

echo "7. 订单查询与关单的状态语义"
q "ALTER TABLE payment_checkout_sessions ADD COLUMN IF NOT EXISTS status varchar(24) NOT NULL DEFAULT 'OPEN';" >/dev/null
q "ALTER TABLE payment_checkout_sessions ADD COLUMN IF NOT EXISTS completed_at timestamptz;" >/dev/null
q "ALTER TABLE payment_checkout_sessions ADD COLUMN IF NOT EXISTS provider_session_ref varchar(255);" >/dev/null
q "ALTER TABLE payment_checkout_sessions ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();" >/dev/null
q "INSERT INTO payment_checkout_sessions (checkout_session_id, organization_id, provider,
      amount_minor, idempotency_key, status)
   VALUES ('ord-open','org-1','ALIPAY_CHECKOUT',12900,'ik-open','OPEN'),
          ('ord-exp','org-1','ALIPAY_CHECKOUT',12900,'ik-exp','EXPIRED');" >/dev/null

lookup() { q "SELECT count(*) FROM payment_checkout_sessions
               WHERE checkout_session_id = '$1' AND status IN ('CREATING','OPEN','COMPLETED');"; }
[[ "$(lookup ord-open)" == "1" ]] && ok "OPEN 订单可查到" || bad "OPEN 订单查不到"
[[ "$(lookup ord-exp)" == "0" ]] && ok "EXPIRED 订单查不到（其上的支付成功回调应进对账）" \
                                 || bad "EXPIRED 订单不该被查到"

close_order() { q "UPDATE payment_checkout_sessions
     SET status='COMPLETED',
         provider_session_ref = COALESCE(provider_session_ref, 'evt-1'),
         completed_at = COALESCE(completed_at, now()), updated_at = now()
   WHERE checkout_session_id='$1' AND organization_id='org-1'
     AND status IN ('CREATING','OPEN','COMPLETED');"; }
matches "$(close_order ord-open)" "UPDATE 1" && ok "首次关单影响 1 行" || bad "首次关单未影响 1 行"
first_completed=$(q "SELECT completed_at FROM payment_checkout_sessions WHERE checkout_session_id='ord-open';")
matches "$(close_order ord-open)" "UPDATE 1" && ok "重发再次关单仍影响 1 行（幂等，不会掉进 ORDER_UNKNOWN）" \
                                             || bad "重发关单未影响 1 行"
second_completed=$(q "SELECT completed_at FROM payment_checkout_sessions WHERE checkout_session_id='ord-open';")
[[ "$first_completed" == "$second_completed" ]] && ok "completed_at 不被重发覆盖（COALESCE 生效）" \
                                                || bad "completed_at 被重发改写了"
matches "$(close_order ord-exp)" "UPDATE 0" && ok "EXPIRED 订单关单影响 0 行 -> 拒绝激活订阅" \
                                            || bad "EXPIRED 订单竟可关闭"
[[ "$(lookup ord-open)" == "1" ]] && ok "关单后仍可查到（COMPLETED 在白名单内）" || bad "关单后查不到了"

echo "8. 运行角色权限"
if q "SELECT 1 FROM pg_roles WHERE rolname='elmos_billing_runtime';" | grep -q 1; then
  privs=$(q "SELECT string_agg(DISTINCT privilege_type, ',' ORDER BY privilege_type)
             FROM information_schema.table_privileges
             WHERE grantee='elmos_billing_runtime'
               AND table_name IN ('payment_callback_receipts','payment_unmatched_callbacks');")
  [[ "$privs" == "INSERT,SELECT" ]] && ok "运行角色只有 INSERT,SELECT（无 UPDATE/DELETE）" \
                                    || bad "运行角色权限为 $privs"
else
  echo "  [SKIP] 未创建 elmos_billing_runtime 角色，跳过权限断言"
fi

echo
if [[ "$FAIL" -gt 0 ]]; then
  echo "DECISION=FAILED  ($PASS 通过, $FAIL 失败)"
  exit 1
fi
echo "DECISION=MIGRATION_VERIFIED_LOCAL  ($PASS 项全部通过)"
echo "  说明：这是本地可销毁库上的工程证据，不代表生产库已应用该迁移。"
