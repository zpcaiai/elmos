#!/usr/bin/env bash
#
# 在合并工作树里跑：
#
#     cd /Users/stephen/DevProjects/AIProjects/elmos-merge
#     bash ../elmos/B-merge-local-perf.sh
#
# 先把刚才的 ruff import 排序落一个提交，再把本地 perf 分支尖端
# （原来那个 "..." 提交，A 脚本清理过）合进来。
set -uo pipefail

[ -e .git ] || { echo "请在 elmos-merge 工作树根目录运行" >&2; exit 1; }

echo "==> 当前 HEAD"
git log --oneline -1

echo
echo "==> 落 ruff 修复"
git add engines/polyglot-route-engine/src/elmos_polyglot_route/assembly.py \
        engines/polyglot-route-engine/tests/test_repository_pipeline.py
if ! git diff --cached --quiet; then
    git commit -q -m "style(route-engine): sort the import blocks the graft left out of order"
    git log --oneline -1
else
    echo "（没有待提交内容，跳过）"
fi

echo
echo "==> 合入本地 perf 分支"
git merge --no-edit perf/analyzer-build-cache-and-batching
rc=$?

echo
echo "==> 冲突文件（$(git diff --name-only --diff-filter=U | wc -l | tr -d ' ') 个）"
git diff --name-only --diff-filter=U
exit "$rc"
