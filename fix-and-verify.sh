#!/usr/bin/env bash
#
#     cd /Users/stephen/DevProjects/AIProjects/elmos-merge
#     bash ../elmos/fix-and-verify.sh 2>&1 | tee /tmp/verify-merge.log
#
# I001 是可自动修复的，所以不再手写替换字符串——直接让 ruff 自己改，
# 改完打印 diff 供审阅，然后跑完整套门禁。
set -uo pipefail

if [ ! -d .git ] && [ ! -f .git ]; then
    echo "请在 elmos-merge 工作树根目录运行" >&2
    exit 1
fi

echo "==> ruff --fix（只允许 import 排序这一类自动修复）"
uv --directory engines/polyglot-route-engine run --locked --group dev \
   ruff check --select I --fix src tests
echo
echo "==> 自动修复改了什么"
git --no-pager diff --stat -- engines/polyglot-route-engine
git --no-pager diff -- engines/polyglot-route-engine | head -80
echo
echo "==> 修复后剩余的 ruff 问题（全部规则）"
uv --directory engines/polyglot-route-engine run --locked --group dev \
   ruff check src tests
echo
echo "================ 进入完整门禁 ================"
exec bash "$(dirname "$0")/verify-merge.sh"
