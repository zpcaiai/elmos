#!/bin/bash
# 清理 AIProjects/ 下 18 个 elmos-* 残留目录 —— v2（2026-09-01 下午）
#
# v1 在第 3 步被自己的门禁拦下，是对的，但拦的理由是判据写错了：
#   `cat-file -e` 在有 alternates 时回答「借得到吗」，而 repack -a 只复制
#   「从本仓库 ref 可达」的对象。**存在 != 可达**，两者被我当成一件事。
#   v1 还只测 HEAD —— 实测漏掉了 production-runtime-continuation 上一条
#   HEAD 之外的未合并分支。v2 改成扫全部 ref，并把缺的那些先 fetch 进来。
#
# 默认 dry-run；加 --apply 才动手。

set -euo pipefail

ROOT="/Users/stephen/DevProjects/AIProjects"
REPO="${ROOT}/elmos"
ARCHIVE="${REPO}/.ai-archive/residue-20260901"
APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1

say() { printf '\n=== %s\n' "$1"; }
run() { if [ "${APPLY}" = "1" ]; then echo "+ $*"; "$@"; else echo "  [dry-run] $*"; fi; }
die() { printf '\nFATAL: %s\n' "$1" >&2; exit 1; }

REPOS="elmos-final-delivery-20260831
elmos-recreated-20260831
elmos-batch32-closeout-20260830
elmos-recovery-20260830-1820
elmos-swift-java-arkui-recovery-20260830
elmos-foundry-recovery-20260830
elmos-production-runtime-continuation"

WORKTREES="elmos-commercial-capability-expansion-v2-recovery
elmos-deepmerge-override-final-20260831
elmos-dependabot-final-20260831
elmos-frontend-skills-closeout-20260830
elmos-frontend-skills-final
elmos-openhands-complete-20260831
elmos-pi-harness-main-merge-20260831"

OTHERS="elmos-deletion-residue-20260830-1818
elmos-dependabot-fix-20260831.ZGLvNd
elmos-polyglot-delivery-20260830
elmos-recreated-git-backup-20260831"

# ---------------------------------------------------------------- 0. 前置
say "0. 前置检查"
cd "${REPO}" || die "进不去 ${REPO}"
[ "$(pwd -P)" = "${REPO}" ] || die "pwd -P 是 $(pwd -P)，不是 ${REPO}"
echo "  cwd(物理) OK"
echo "  可用空间 $(df -h . | awk 'NR==2 {print $4}')"

ALT=".git/objects/info/alternates"
[ -f "${ALT}" ] && die "还存在 alternates。v2 假定 v1 已经 repack 并把它挪开了，请先确认状态。"
echo "  无 alternates —— elmos 已解耦（v1 的 repack 生效了）"

BEFORE_HEAD=$(git rev-parse HEAD)
echo "  HEAD = ${BEFORE_HEAD}"

say "0b. 确认 elmos 自足（这一步替代 v1 那个写错的判据）"
if [ "${APPLY}" = "1" ]; then
  git fsck --connectivity-only --no-dangling --no-progress || die "fsck 不过，先别删任何东西"
  echo "  fsck rc=0 OK"
else
  echo "  [dry-run] --apply 时会跑 fsck"
fi

# ---------------------------------------------------------------- 1. 抢救
say "1. 抢救独有文件"
run mkdir -p "${ARCHIVE}"
S1="${ROOT}/elmos-recreated-git-backup-20260831/integrate_polyglot_semantic_assurance_skills.py"
[ -f "${S1}" ] && [ ! -f "${ARCHIVE}/integrate_polyglot_semantic_assurance_skills.RECREATED-BACKUP.py" ] \
  && run cp -p "${S1}" "${ARCHIVE}/integrate_polyglot_semantic_assurance_skills.RECREATED-BACKUP.py"
S2="${ROOT}/elmos-polyglot-delivery-20260830/DELIVERY.md"
[ -f "${S2}" ] && [ ! -f "${ARCHIVE}/POLYGLOT-DELIVERY.md" ] && run cp -p "${S2}" "${ARCHIVE}/POLYGLOT-DELIVERY.md"
S3="${ROOT}/elmos-polyglot-delivery-20260830/0001-feat-polyglot-productionize-semantic-assurance-skill.patch"
[ -f "${S3}" ] && [ ! -f "${ARCHIVE}/$(basename "${S3}")" ] && run cp -p "${S3}" "${ARCHIVE}/"

# ------------------------------------------------- 2. 全 ref 扫描 + 补 fetch
say "2. 扫描 7 个 repo 的全部分支，把 elmos 缺的 fetch 进来"
echo "  （v1 只测 HEAD —— 实测会漏掉 HEAD 之外的未合并分支）"
: > /tmp/residue-missing.txt   # 每次跑都清空，否则第二次会累积上一次的条目
for d in ${REPOS}; do
  [ -d "${ROOT}/${d}/.git" ] || continue
  find "${ROOT}/${d}/.git/refs/heads" -type f 2>/dev/null | while read -r rf; do
    name="${rf##*refs/heads/}"; sha=$(cat "${rf}")
    if ! git cat-file -e "${sha}^{commit}" 2>/dev/null; then
      printf '  缺: %-52s %s  <- %s\n' "${name}" "${sha:0:9}" "${d}"
      echo "${d} ${name}" >> /tmp/residue-missing.txt
    fi
  done
done
if [ -s /tmp/residue-missing.txt ]; then
  while read -r d name; do
    run git fetch --no-tags "${ROOT}/${d}" "refs/heads/${name}:refs/residue/${d}/${name}"
  done < /tmp/residue-missing.txt
fi

say "2b. 复验：现在所有分支都必须在 elmos 里"
if [ "${APPLY}" = "1" ]; then
  BAD=0
  for d in ${REPOS}; do
    [ -d "${ROOT}/${d}/.git" ] || continue
    while read -r rf; do
      sha=$(cat "${rf}"); name="${rf##*refs/heads/}"
      git cat-file -e "${sha}^{commit}" 2>/dev/null \
        || { printf '  仍然缺: %s %s (%s)\n' "${sha:0:9}" "${name}" "${d}"; BAD=1; }
    done < <(find "${ROOT}/${d}/.git/refs/heads" -type f 2>/dev/null)
  done
  [ "${BAD}" = "0" ] || die "还有分支没进来，不删。"
  echo "  全部分支已在 elmos —— 删除不会丢任何提交"
  [ "$(git rev-parse HEAD)" = "${BEFORE_HEAD}" ] || die "HEAD 变了"
else
  echo "  [dry-run] --apply 时这是硬门禁"
fi

# ---------------------------------------------------------------- 3. 删除
say "3. 清掉指向 /private/tmp 的失效 worktree 注册"
run git worktree prune -v

say "4. 删除：先 worktree，再 repo 与其余"
for d in ${WORKTREES}; do [ -e "${ROOT}/${d}" ] && run rm -rf "${ROOT}/${d}"; done
for d in ${OTHERS};    do [ -e "${ROOT}/${d}" ] && run rm -rf "${ROOT}/${d}"; done
for d in ${REPOS};     do [ -e "${ROOT}/${d}" ] && run rm -rf "${ROOT}/${d}"; done

say "5. 收尾"
if [ "${APPLY}" = "1" ]; then
  echo "  还剩:"; ls -d "${ROOT}"/elmos-* 2>/dev/null | sed 's/^/    /' || echo "    （已清空）"
  echo "  HEAD = $(git rev-parse --short HEAD)  分支 = $(git rev-parse --abbrev-ref HEAD)"
  echo "  抢救进来的分支:"; git for-each-ref --format='    %(refname)' refs/residue 2>/dev/null
  echo "  可用空间 = $(df -h . | awk 'NR==2 {print $4}')"
  echo "  确认无误可删备份: rm ${REPO}/${ALT}.disabled-20260901"
else
  printf '\n  以上是 dry-run。确认后跑:\n    bash %s --apply\n' "${REPO}/cleanup-elmos-residue.sh"
fi
