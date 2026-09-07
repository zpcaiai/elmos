#!/usr/bin/env bash
# 订阅激活路径的端到端验证（针对完整迁移链 V1–V54 的真实 schema）
#
# 上一轮只验证了「关单」那半段 SQL；这一轮把 SubscriptionActivator 实际执行的
# 三条语句在真库上按同样顺序、同样参数跑一遍：
#
#   set_config('app.organization_id', ..., true)
#     → UPDATE payment_checkout_sessions ... 关单
#       → SELECT elmos_activate_subscription_period(...)
#
# 断言的是**跨表的最终状态**：订阅、额度分配、订阅事件三张表是否一致，
# 以及重放与非法输入是否被正确拒绝。
#
# 只在可销毁数据库上运行。
#
# 用法：
#   ELMOS_ACTIVATION_VERIFY_DB=elmos_full \
#   ELMOS_ACTIVATION_VERIFY_DSN="-h 127.0.0.1 -p 5432 -U postgres" \
#   ELMOS_ACTIVATION_VERIFY_DISPOSABLE_CONFIRMED=true \
#     bash tooling/payment-db-verify/verify_subscription_activation.sh
set -Eeuo pipefail

DSN="${ELMOS_ACTIVATION_VERIFY_DSN:-}"
DB="${ELMOS_ACTIVATION_VERIFY_DB:-}"
[[ -n "$DSN" && -n "$DB" ]] || { echo "REFUSED: 需设置 DSN 与 DB" >&2; exit 2; }
[[ "${ELMOS_ACTIVATION_VERIFY_DISPOSABLE_CONFIRMED:-}" == "true" ]] || {
  echo "REFUSED: 需显式确认目标库可销毁" >&2; exit 2; }

PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  [PASS] %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  [FAIL] %s\n' "$1"; }
q()   { psql $DSN -d "$DB" -tA -c "$1" 2>&1 || true; }
matches() { [[ "$1" == *"$2"* ]]; }

ORG="org-activation-$$"
PLAN="elmos-pro-monthly"
ORDER_ID="ord-act-$$"
EVENT_ID="evt-act-$$"
SUB="sub-act-$$"
ALLOC="qa-act-$$"

# ---------------------------------------------------------------------------
# 前置：组织与一笔支付宝订单
# ---------------------------------------------------------------------------
q "INSERT INTO organizations (organization_id) VALUES ('$ORG')
     ON CONFLICT DO NOTHING;" >/dev/null
q "INSERT INTO payment_checkout_sessions (
      checkout_session_id, organization_id, actor_id, plan_id, catalog_version,
      currency, amount_minor, provider, status, expires_at,
      idempotency_key, request_hash)
   VALUES ('$ORDER_ID','$ORG','actor-system','$PLAN','2026-07-28.2',
      'CNY',12900,'ALIPAY_CHECKOUT','OPEN', now() + interval '1 hour',
      'ik-$ORDER_ID', repeat('a',64));" >/dev/null

# SubscriptionActivator 实际执行的三条语句，包在一个事务里
activate() {
  local sub="$1" alloc="$2" start="$3" end="$4" event="$5" plan="${6:-$PLAN}"
  psql $DSN -d "$DB" -tA -v ON_ERROR_STOP=1 2>&1 <<SQL || true
BEGIN;
SELECT set_config('app.organization_id', '$ORG', true);
UPDATE payment_checkout_sessions
   SET status='COMPLETED',
       provider_session_ref = COALESCE(provider_session_ref, '$event'),
       completed_at = COALESCE(completed_at, now()),
       updated_at = now()
 WHERE checkout_session_id='$ORDER_ID' AND organization_id='$ORG'
   AND status IN ('CREATING','OPEN','COMPLETED');
SELECT elmos_activate_subscription_period(
    '$sub', '$alloc', 'actor-system', '$plan', 'ALIPAY_CHECKOUT',
    '$ORG', 'alipay_checkout:$ORDER_ID',
    '$start'::timestamptz, '$end'::timestamptz, '$event', 'ALIPAY_CHECKOUT:$event');
COMMIT;
SQL
}

echo "1. 首次激活（支付宝通道走完整存储函数）"
out=$(activate "$SUB" "$ALLOC" "2026-09-01T00:00:00Z" "2026-10-02T00:00:00Z" "$EVENT_ID")
matches "$out" "ERROR" && { bad "激活报错: $(echo "$out" | grep ERROR | head -1)"; } \
                       || ok "激活执行无错误"

row=$(q "SELECT status||'|'||plan_id||'|'||provider||'|'||price_minor||'|'||
                to_char(current_period_end,'YYYY-MM-DD')
           FROM subscriptions WHERE subscription_id='$SUB';")
[[ "$row" == "ACTIVE|$PLAN|ALIPAY_CHECKOUT|12900|2026-10-02" ]] \
  && ok "订阅为 ACTIVE，套餐/通道/价格/期末均正确（${row}）" \
  || bad "订阅行不符：$row"

alloc=$(q "SELECT status||'|'||token_limit||'|'||credit_limit
             FROM quota_allocations WHERE quota_allocation_id='$ALLOC';")
[[ "$alloc" == "ACTIVE|20000000|600" ]] \
  && ok "额度分配已创建且取自目录（2000 万 token / 600 Credit）" \
  || bad "额度分配不符：$alloc"

evt=$(q "SELECT count(*) FROM subscription_events
          WHERE subscription_id='$SUB' AND event_type='INVOICE_PAID';")
[[ "$evt" == "1" ]] && ok "订阅事件已记录（1 条 INVOICE_PAID）" || bad "订阅事件数为 $evt"

closed=$(q "SELECT status FROM payment_checkout_sessions WHERE checkout_session_id='$ORDER_ID';")
[[ "$closed" == "COMPLETED" ]] && ok "订单已关闭" || bad "订单状态为 $closed"

echo
echo "2. 重放同一回调（提供方重发）"
before_ver=$(q "SELECT state_version FROM subscriptions WHERE subscription_id='$SUB';")
out=$(activate "$SUB" "$ALLOC" "2026-09-01T00:00:00Z" "2026-10-02T00:00:00Z" "$EVENT_ID")
matches "$out" "ERROR" && bad "重放报错" || ok "重放不报错"
allocs=$(q "SELECT count(*) FROM quota_allocations WHERE subscription_id='$SUB';")
[[ "$allocs" == "1" ]] && ok "额度分配仍只有 1 条（不会重复发放额度）" || bad "额度分配变成 $allocs 条"
evts=$(q "SELECT count(*) FROM subscription_events WHERE subscription_id='$SUB';")
[[ "$evts" == "1" ]] && ok "订阅事件仍只有 1 条" || bad "订阅事件变成 $evts 条"
subs=$(q "SELECT count(*) FROM subscriptions WHERE organization_id='$ORG';")
[[ "$subs" == "1" ]] && ok "订阅仍只有 1 条" || bad "订阅变成 $subs 条"

echo
echo "3. 续费（同一订阅 ID，新期间）"
out=$(activate "$SUB" "qa-renew-$$" "2026-10-02T00:00:00Z" "2026-11-02T00:00:00Z" "evt-renew-$$")
matches "$out" "ERROR" && bad "续费报错: $(echo "$out"|grep ERROR|head -1)" || ok "续费执行无错误"
newend=$(q "SELECT to_char(current_period_end,'YYYY-MM-DD') FROM subscriptions WHERE subscription_id='$SUB';")
[[ "$newend" == "2026-11-02" ]] && ok "订阅期间被推后（${newend}），而不是新建一条订阅" \
                                || bad "续费后期末为 $newend"
subs=$(q "SELECT count(*) FROM subscriptions WHERE organization_id='$ORG';")
[[ "$subs" == "1" ]] && ok "组织下仍只有 1 条订阅" || bad "订阅变成 $subs 条"
allocs=$(q "SELECT count(*) FROM quota_allocations WHERE subscription_id='$SUB';")
[[ "$allocs" == "2" ]] && ok "新期间产生新的额度分配（共 2 条）" || bad "额度分配为 $allocs 条"

echo
echo "4. 失败关闭：非法输入必须被拒"
out=$(activate "sub-bad-$$" "qa-bad-$$" "2026-09-01T00:00:00Z" "2026-08-01T00:00:00Z" "evt-bad1-$$")
matches "$out" "BILLING_PERIOD_INVALID" && ok "期末早于期初 -> BILLING_PERIOD_INVALID" \
                                       || bad "非法期间未被拒：$(echo "$out"|head -2)"

out=$(activate "sub-trial-$$" "qa-trial-$$" "2026-09-01T00:00:00Z" "2026-09-15T00:00:00Z" "evt-bad2-$$" "elmos-free-trial")
matches "$out" "PAID_PLAN_INVALID" && ok "免费体验套餐 -> PAID_PLAN_INVALID（付款不能激活试用）" \
                                  || bad "试用套餐未被拒：$(echo "$out"|head -2)"

out=$(activate "sub-nx-$$" "qa-nx-$$" "2026-09-01T00:00:00Z" "2026-10-01T00:00:00Z" "evt-bad3-$$" "elmos-nonexistent")
matches "$out" "PAID_PLAN_INVALID" && ok "不存在的套餐 -> PAID_PLAN_INVALID" \
                                  || bad "未知套餐未被拒：$(echo "$out"|head -2)"

echo
echo "5. 租户上下文缺失必须失败关闭"
out=$(psql $DSN -d "$DB" -tA -v ON_ERROR_STOP=1 2>&1 <<SQL || true
BEGIN;
SELECT elmos_activate_subscription_period(
    'sub-noctx-$$', 'qa-noctx-$$', 'actor-system', '$PLAN', 'ALIPAY_CHECKOUT',
    '$ORG', 'alipay_checkout:x',
    '2026-09-01T00:00:00Z'::timestamptz, '2026-10-01T00:00:00Z'::timestamptz,
    'evt-noctx-$$', 'ALIPAY_CHECKOUT:evt-noctx-$$');
COMMIT;
SQL
)
matches "$out" "TENANT_CONTEXT_REQUIRED" \
  && ok "未设 app.organization_id -> TENANT_CONTEXT_REQUIRED（证明必须同事务设上下文）" \
  || bad "缺租户上下文未被拒：$(echo "$out"|head -2)"

echo
echo "6. 事务性：关单失败时不得留下订阅"
q "INSERT INTO payment_checkout_sessions (
      checkout_session_id, organization_id, actor_id, plan_id, catalog_version,
      currency, amount_minor, provider, status, expires_at, idempotency_key, request_hash)
   VALUES ('ord-exp-$$','$ORG','actor-system','$PLAN','2026-07-28.2','CNY',12900,
      'ALIPAY_CHECKOUT','EXPIRED', now(), 'ik-exp-$$', repeat('b',64));" >/dev/null
before=$(q "SELECT count(*) FROM subscriptions WHERE organization_id='$ORG';")
out=$(psql $DSN -d "$DB" -tA -v ON_ERROR_STOP=1 2>&1 <<SQL || true
BEGIN;
SELECT set_config('app.organization_id', '$ORG', true);
DO \$do\$
DECLARE changed int;
BEGIN
  UPDATE payment_checkout_sessions SET status='COMPLETED', updated_at=now()
   WHERE checkout_session_id='ord-exp-$$' AND organization_id='$ORG'
     AND status IN ('CREATING','OPEN','COMPLETED');
  GET DIAGNOSTICS changed = ROW_COUNT;
  IF changed <> 1 THEN RAISE EXCEPTION 'ORDER_NOT_CLOSEABLE'; END IF;
END
\$do\$;
SELECT elmos_activate_subscription_period(
    'sub-exp-$$', 'qa-exp-$$', 'actor-system', '$PLAN', 'ALIPAY_CHECKOUT',
    '$ORG', 'alipay_checkout:ord-exp-$$',
    '2026-09-01T00:00:00Z'::timestamptz, '2026-10-01T00:00:00Z'::timestamptz,
    'evt-exp-$$', 'ALIPAY_CHECKOUT:evt-exp-$$');
COMMIT;
SQL
)
matches "$out" "ORDER_NOT_CLOSEABLE" && ok "EXPIRED 订单关单失败并中止" || bad "EXPIRED 订单未中止"
after=$(q "SELECT count(*) FROM subscriptions WHERE organization_id='$ORG';")
[[ "$before" == "$after" ]] && ok "回滚后订阅数不变（${after}），没有留下孤儿订阅" \
                            || bad "订阅数从 $before 变成 $after"

echo
if [[ "$FAIL" -gt 0 ]]; then
  echo "DECISION=FAILED  ($PASS 通过, $FAIL 失败)"; exit 1
fi
echo "DECISION=ACTIVATION_VERIFIED_LOCAL  ($PASS 项全部通过)"
echo "  说明：本地可销毁库上的工程证据，不代表生产库已验证。"
