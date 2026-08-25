#!/usr/bin/env bash
#
# 在 elmos 主克隆里跑（分支 perf/analyzer-build-cache-and-batching）：
#
#     cd /Users/stephen/DevProjects/AIProjects/elmos
#     bash A-clean-perf-tip.sh
#
# 目的：本地那个 subject 为 "..." 的提交是 `git add -A` 扫进来的，
# 里面混了 pytest 的 basetemp 目录和这次合并用的临时脚本。
# 它还没 push，所以直接 amend 成一个干净提交，工作区文件一个都不删。
set -euo pipefail

BRANCH=perf/analyzer-build-cache-and-batching
[ "$(git rev-parse --abbrev-ref HEAD)" = "$BRANCH" ] || { echo "请先 git switch $BRANCH" >&2; exit 1; }

echo "==> 先留一个回滚锚点"
git branch -f backup/perf-preclean HEAD
git rev-parse --short backup/perf-preclean

echo "==> 从索引里摘掉临时产物（工作区文件保留）"
git rm -r -q --cached --ignore-unmatch \
    .matrix223-python-let-candidate.xU9hBY \
    _merge_conflicts
git rm -q --cached --ignore-unmatch \
    verify-merge.sh commit-perf-merge.sh fix-lint.py \
    resolve-merge.py regenerate-inventory.sh \
    fix-and-verify.sh A-clean-perf-tip.sh B-merge-local-perf.sh \
    MERGE_NOTES_perf_into_main.md

echo "==> 让它们以后不再被扫进来"
for p in '/.matrix223-*/' '/_merge_conflicts/' '/verify-merge.sh' '/commit-perf-merge.sh' \
         '/fix-lint.py' '/resolve-merge.py' '/regenerate-inventory.sh' \
         '/fix-and-verify.sh' '/A-clean-perf-tip.sh' '/B-merge-local-perf.sh' \
         '/MERGE_NOTES_perf_into_main.md'; do
    grep -qxF "$p" .gitignore 2>/dev/null || echo "$p" >> .gitignore
done
git add .gitignore

echo "==> amend（提交内容不变，只是去掉临时产物 + 换个说得清的标题）"
git commit --quiet --amend -m "feat(route-engine): repository language lifecycle, thirteen-language matrix, and the skill/verification-pack import batch

把工作区里已经跑通、但一直没提交的那批改动固化下来。其中
models.py 的 REPOSITORY_LANGUAGE_LIFECYCLE_* 与 repository_language_lifecycle()
是 assembly.py 早就在 import 的符号——没有它们，engine 连 import 都过不去。"

echo
echo "==> 结果"
git log --oneline -1
git show --stat HEAD | tail -3
echo
echo "确认临时产物已不在提交里（下面应当没有输出）："
git show --name-only --format= HEAD | grep -E '^(\.matrix223|_merge_conflicts/|verify-merge\.sh|commit-perf-merge\.sh|fix-lint\.py|resolve-merge\.py|regenerate-inventory\.sh)' || echo "  （干净）"
