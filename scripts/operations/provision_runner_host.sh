#!/usr/bin/env bash
# ELMOS rootless Runner 主机预置与校验
#
# 状态：本脚本的 --check 模式已在无 podman 的环境验证过失败关闭行为；
#       --apply 模式尚未在真实 Runner 主机执行（RISK-DEPLOY-001 保持 OPEN）。
#
# 用法：
#   ./provision_runner_host.sh --check                 # 只读检查，不改动系统
#   sudo ./provision_runner_host.sh --apply            # 创建用户、目录、subuid/subgid
#
# 环境变量（--apply 必须显式提供，不提供默认值以免误建目录）：
#   ELMOS_RUNNER_USER   运行 Runner 的专用系统用户名，例如 elmos-runner
#   ELMOS_RUNNER_ROOT   Runner 专用根目录绝对路径，例如 /srv/elmos/runner
#
# 失败关闭：任何一项前置条件不满足，--check 以退出码 3 结束，且不输出"通过"。
set -Eeuo pipefail

MODE=""
FAILURES=0
CHECKS=0

usage() { sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }

case "${1:-}" in
  --check) MODE=check ;;
  --apply) MODE=apply ;;
  *) usage ;;
esac

pass() { CHECKS=$((CHECKS+1)); printf '  [ok]   %s\n' "$1"; }
fail() { CHECKS=$((CHECKS+1)); FAILURES=$((FAILURES+1)); printf '  [MISS] %s\n' "$1"; }
info() { printf '         %s\n' "$1"; }

# --- 危险路径守卫：绝不允许把仓库根或系统根当作 Runner 根 -------------------
assert_safe_root() {
  local root="$1"
  case "$root" in
    ""|"/"|"/root"|"/home"|"/usr"|"/etc"|"/var"|"/opt"|"/srv")
      printf 'REFUSED: ELMOS_RUNNER_ROOT=%s 是系统目录或过于宽泛\n' "$root" >&2; exit 4 ;;
  esac
  [[ "$root" = /* ]] || { printf 'REFUSED: ELMOS_RUNNER_ROOT 必须是绝对路径\n' >&2; exit 4; }
  if [[ -e "$root/.git" ]]; then
    printf 'REFUSED: %s 是一个 Git 仓库根，不能作为 Runner 根\n' "$root" >&2; exit 4
  fi
  # 拒绝把 Runner 根设成仓库的祖先目录
  if [[ -n "${ELMOS_REPOSITORY_ROOT:-}" ]]; then
    case "${ELMOS_REPOSITORY_ROOT}/" in
      "$root"/*) printf 'REFUSED: Runner 根是仓库根的祖先目录\n' >&2; exit 4 ;;
    esac
  fi
}

echo "ELMOS Runner 主机 [$MODE]"
echo

# --- 1. 容器引擎 -----------------------------------------------------------
echo "1. 容器引擎"
ENGINE=""
for candidate in /usr/bin/podman /usr/local/bin/podman /usr/bin/docker; do
  if [[ -x "$candidate" ]]; then ENGINE="$candidate"; break; fi
done
if [[ -n "$ENGINE" ]]; then
  pass "找到容器引擎：$ENGINE"
  info "ELMOS_LOCAL_RUNNER_CONTAINER_ENGINE=$ENGINE"
  if [[ "$ENGINE" == *podman ]] && "$ENGINE" info --format '{{.Host.Security.Rootless}}' 2>/dev/null | grep -qx true; then
    pass "podman 以 rootless 模式运行"
  else
    fail "未确认 rootless 模式（生产要求 rootless）"
  fi
else
  fail "未找到 podman/docker 可执行文件"
  info "生产模式唯一允许 ELMOS_LOCAL_RUNNER_EXECUTOR=ROOTLESS_CONTAINER"
fi

# --- 2. 专用用户与 subuid/subgid -------------------------------------------
echo
echo "2. 专用用户与用户命名空间"
RUNNER_USER="${ELMOS_RUNNER_USER:-}"
if [[ -z "$RUNNER_USER" ]]; then
  fail "未设置 ELMOS_RUNNER_USER"
elif id "$RUNNER_USER" >/dev/null 2>&1; then
  pass "用户存在：$RUNNER_USER"
  if grep -q "^${RUNNER_USER}:" /etc/subuid 2>/dev/null; then
    pass "/etc/subuid 已为 $RUNNER_USER 分配区间"
  else
    fail "/etc/subuid 缺少 $RUNNER_USER 的区间（rootless 容器无法映射用户）"
  fi
  if grep -q "^${RUNNER_USER}:" /etc/subgid 2>/dev/null; then
    pass "/etc/subgid 已为 $RUNNER_USER 分配区间"
  else
    fail "/etc/subgid 缺少 $RUNNER_USER 的区间"
  fi
else
  fail "用户不存在：$RUNNER_USER"
fi

# --- 3. Runner 根目录 ------------------------------------------------------
echo
echo "3. Runner 根目录"
RUNNER_ROOT="${ELMOS_RUNNER_ROOT:-}"
if [[ -z "$RUNNER_ROOT" ]]; then
  fail "未设置 ELMOS_RUNNER_ROOT"
else
  assert_safe_root "$RUNNER_ROOT"
  if [[ -d "$RUNNER_ROOT" ]]; then
    pass "目录存在：$RUNNER_ROOT"
    perms="$(stat -c '%a' "$RUNNER_ROOT" 2>/dev/null || stat -f '%A' "$RUNNER_ROOT")"
    if [[ "$perms" == "700" || "$perms" == "750" ]]; then
      pass "权限为 $perms"
    else
      fail "权限为 $perms（应为 700 或 750）"
    fi
  else
    fail "目录不存在：$RUNNER_ROOT"
  fi
fi

# --- 4. 内核能力 -----------------------------------------------------------
echo
echo "4. 内核前置"
if [[ -f /proc/sys/user/max_user_namespaces ]]; then
  ns="$(cat /proc/sys/user/max_user_namespaces 2>/dev/null || echo "")"
  # 必须先确认是纯数字：在 set -u 下把非数字喂给 [[ -gt ]] 会被当成变量名，
  # 脚本会以 "unbound variable" 直接崩掉，而不是给出 NOT_READY 判定。
  if [[ "$ns" =~ ^[0-9]+$ ]]; then
    if [[ "$ns" -gt 0 ]]; then pass "user namespaces 可用（max=$ns）"
    else fail "user namespaces 被禁用（max=0），rootless 容器无法启动"; fi
  else
    fail "max_user_namespaces 内容异常：${ns:-<空>}"
  fi
else
  fail "无法读取 /proc/sys/user/max_user_namespaces（非 Linux 或内核不支持）"
fi
if [[ -f /proc/self/cgroup ]]; then pass "cgroup 可读（资源限额前置）"
else fail "无法读取 /proc/self/cgroup"; fi

# --- 5. 作业容器硬化基线（声明，不执行） ------------------------------------
echo
echo "5. 作业容器必须使用的硬化参数（每次作业都要带全）"
cat <<'BASELINE'
         --rm
         --network=none                  # 默认拒绝出网
         --read-only                     # 只读根文件系统
         --cap-drop=ALL
         --security-opt=no-new-privileges
         --user <非 root uid>:<gid>
         --pids-limit=512
         --memory=<上限>  --cpus=<上限>
         --tmpfs /tmp:rw,noexec,nosuid,size=<上限>
         --mount type=bind,src=<源码>,dst=/src,ro=true
         镜像必须写成 name@sha256:<64 hex>，禁止可变标签
BASELINE
info "任一参数缺失即视为隔离未成立，不得执行客户派生的构建"

# --- apply ------------------------------------------------------------------
if [[ "$MODE" == "apply" ]]; then
  echo
  echo "6. 应用变更"
  [[ "$(id -u)" -eq 0 ]] || { echo "REFUSED: --apply 需要 root" >&2; exit 4; }
  [[ "$(uname -s)" == "Linux" ]] || {
    echo "REFUSED: --apply 依赖 useradd/usermod --add-subuids，仅支持 Linux" >&2; exit 4; }
  for tool in useradd usermod install; do
    command -v "$tool" >/dev/null 2>&1 || {
      echo "REFUSED: 缺少 $tool" >&2; exit 4; }
  done
  [[ -n "$RUNNER_USER" && -n "$RUNNER_ROOT" ]] || {
    echo "REFUSED: --apply 必须显式提供 ELMOS_RUNNER_USER 与 ELMOS_RUNNER_ROOT" >&2; exit 4; }
  assert_safe_root "$RUNNER_ROOT"
  id "$RUNNER_USER" >/dev/null 2>&1 || {
    # nologin 路径按发行版不同：Debian 系在 /usr/sbin，RHEL 系在 /sbin
    NOLOGIN=""
    for candidate in /usr/sbin/nologin /sbin/nologin /bin/false; do
      [[ -x "$candidate" ]] && { NOLOGIN="$candidate"; break; }
    done
    [[ -n "$NOLOGIN" ]] || { echo "REFUSED: 找不到 nologin/false" >&2; exit 4; }
    useradd --system --create-home --shell "$NOLOGIN" "$RUNNER_USER"
    echo "  已创建用户 $RUNNER_USER"; }
  grep -q "^${RUNNER_USER}:" /etc/subuid || {
    usermod --add-subuids 200000-265535 "$RUNNER_USER"; echo "  已分配 subuid"; }
  grep -q "^${RUNNER_USER}:" /etc/subgid || {
    usermod --add-subgids 200000-265535 "$RUNNER_USER"; echo "  已分配 subgid"; }
  install -d -m 700 -o "$RUNNER_USER" -g "$RUNNER_USER" "$RUNNER_ROOT"
  echo "  已确保目录 $RUNNER_ROOT (700, $RUNNER_USER)"
  command -v loginctl >/dev/null 2>&1 && loginctl enable-linger "$RUNNER_USER" || true
  echo "  完成。请重新运行 --check 确认。"
fi

# --- 结论 -------------------------------------------------------------------
echo
if [[ "$FAILURES" -gt 0 ]]; then
  echo "DECISION=NOT_READY  （$FAILURES/$CHECKS 项未满足）"
  echo "  未满足项不得以'稍后补上'为由继续部署 Runner。"
  exit 3
fi
echo "DECISION=HOST_PRECONDITIONS_MET  （$CHECKS 项全部满足）"
echo "  说明：这只是主机前置条件，不构成隔离证据。"
echo "  真实隔离仍需按第 5 节参数启动作业容器并留下可复算的执行证据。"
