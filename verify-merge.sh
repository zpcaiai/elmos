#!/usr/bin/env bash
#
# Run every gate the perf->main merge has to pass, in the order where an early
# failure makes the later output meaningless. Nothing here modifies the tree.
#
#     cd /Users/stephen/DevProjects/AIProjects/elmos-merge
#     bash ../elmos/verify-merge.sh 2>&1 | tee /tmp/verify-merge.log
#
# Each gate prints PASS/FAIL and keeps going, so one run gives the whole picture.
# The full output of every gate is under /tmp/verify-merge/.

set -uo pipefail
OUT=/tmp/verify-merge
rm -rf "$OUT" && mkdir -p "$OUT"
declare -a NAMES STATUS

run() {
    local name="$1"; shift
    printf '\n\033[1m==> %s\033[0m\n' "$name"
    if "$@" > "$OUT/$name.log" 2>&1; then
        printf '    PASS\n'
        NAMES+=("$name"); STATUS+=(PASS)
    else
        printf '    FAIL  (see %s/%s.log)\n' "$OUT" "$name"
        tail -25 "$OUT/$name.log" | sed 's/^/    | /'
        NAMES+=("$name"); STATUS+=(FAIL)
    fi
}

if [ ! -d .git ] && [ ! -f .git ]; then
    echo "run this from the elmos-merge worktree root" >&2
    exit 1
fi

echo "分支: $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'detached')"
echo "未解决冲突: $(git diff --name-only --diff-filter=U | wc -l | tr -d ' ')"

# --- 静态检查先行：它们最快，而且能定位嫁接接缝 ---
run ruff-engine   uv --directory engines/polyglot-route-engine run --locked --group dev ruff check src tests
run mypy-engine   uv --directory engines/polyglot-route-engine run --locked --group dev mypy src

# --- 引擎测试 ---
run pytest-engine uv --directory engines/polyglot-route-engine run --locked --group dev pytest -q

# --- 其它引擎 ---
run pytest-synthesis uv --directory engines/project-synthesis-engine run --locked pytest -q

# --- 前端：tsc + next build + 九条策略/测试 ---
run web-console-check pnpm --dir apps/web-console check

# --- Java ---
run mvn-worker mvn -q -pl apps/java-engine-worker test
run mvn-arch   mvn -q -pl modules/architecture-tests test

# --- 三个自计数校验器：它们的输出直接给出该写的数字 ---
run makefile-portability python3 scripts/operations/validate_makefile_portability.py
run route-matrix        python3 scripts/operations/validate_translation_route_matrix.py
run mature-series       python3 scripts/validate_mature_product_series.py

printf '\n\033[1m===== 汇总 =====\033[0m\n'
fail=0
for i in "${!NAMES[@]}"; do
    printf '  %-22s %s\n' "${NAMES[$i]}" "${STATUS[$i]}"
    [ "${STATUS[$i]}" = FAIL ] && fail=$((fail + 1))
done
printf '\n%d 个门禁失败，全部日志在 %s/\n' "$fail" "$OUT"
if [ "$fail" -eq 0 ]; then
    echo
    echo "全绿。提交前仍需处理三件（见 MERGE_NOTES_perf_into_main.md）："
    echo "  1. ELMOS_INTEGRATION_MANIFEST.json 的计数与 sha256 必须重新生成（现为占位）"
    echo "  2. README 与 BUSINESS_LINE_CLOSURE_MATRIX 的路线条数，按 route-matrix 的输出改"
    echo "  3. validate_mature_product_series 的 schema 计数，按它的输出改"
fi
exit "$fail"
