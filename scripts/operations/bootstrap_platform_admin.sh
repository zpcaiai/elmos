#!/usr/bin/env bash
# 引导第一个平台管理员。
#
# 为什么是脚本而不是 elmosctl 的一个子命令
# ----------------------------------------
# elmosctl 刻意不执行任何东西——它的每条命令都返回
# ACCEPTED_FOR_EXTERNAL_EXECUTION / RUN_IN_APPROVED_PRIVATE_ENVIRONMENT，
# 是一道策略门而不是执行器。往里塞一个真写库的命令，会给它加上一条新的数据库
# 凭据路径，也和它「自己什么都不做」的定位冲突。
#
# 而引导这件事本来就要求直连数据库的会话——那个权限等级本来就能手改这张表。
# 这个脚本相对于手改的全部价值在于：它调的是 elmos_platform_bootstrap_admin，
# 那个函数会拒绝第二次引导，并留下一条审计。
#
# 用法：
#   ELMOS_DATABASE_URL='postgres://…' \
#     scripts/operations/bootstrap_platform_admin.sh <account_id> "<reason>"
#
# 之后所有的授予/撤销都走 /admin 里那条带审计的路径，不要再用这个脚本。

set -euo pipefail

ACCOUNT_ID="${1:-}"
REASON="${2:-}"

if [[ -z "$ACCOUNT_ID" || -z "$REASON" ]]; then
    echo "用法: $0 <account_id> \"<reason>\"" >&2
    echo "reason 是必填的：授予跨租户读取权限而不记录原因，" >&2
    echo "这份名单以后就没法复核了。" >&2
    exit 2
fi

if [[ -z "${ELMOS_DATABASE_URL:-}" ]]; then
    echo "ELMOS_DATABASE_URL 未设置。" >&2
    exit 2
fi

# jdbc: 前缀是 Java 侧的写法，psql 不认。
PSQL_URL="${ELMOS_DATABASE_URL#jdbc:}"

echo "将把 ${ACCOUNT_ID} 引导为 PLATFORM_APPROVER。"
echo "理由: ${REASON}"
echo
read -r -p "确认？输入 yes 继续: " CONFIRM
if [[ "$CONFIRM" != "yes" ]]; then
    echo "已取消。" >&2
    exit 1
fi

# 单条语句、参数化传入，避免把 reason 拼进 SQL。
RESULT=$(psql "$PSQL_URL" -v ON_ERROR_STOP=1 -t -A \
    -v account="$ACCOUNT_ID" -v reason="$REASON" \
    -c "SELECT elmos_platform_bootstrap_admin(:'account', :'reason');")

case "$RESULT" in
    ALLOWED)
        echo "完成：${ACCOUNT_ID} 现在是 PLATFORM_APPROVER。"
        echo "审计已记录在 platform_admin_access_log（operation=BOOTSTRAP_ADMIN）。"
        echo
        echo "后续的管理员授予请走 /admin 界面——那条路径要求授予人本身是 APPROVER，"
        echo "并且同样会留审计。"
        ;;
    DENIED_POLICY)
        echo "被拒绝。可能的原因：" >&2
        echo "  · 已经存在一个在册的 PLATFORM_APPROVER —— 引导入口只开一次，" >&2
        echo "    此后授予必须走带审计的路径；" >&2
        echo "  · account_id 不存在；" >&2
        echo "  · reason 为空。" >&2
        exit 4
        ;;
    *)
        echo "未预期的返回: ${RESULT}" >&2
        exit 5
        ;;
esac
