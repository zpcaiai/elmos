#!/usr/bin/env bash
#
# perf->main 合并门禁：跑一遍 + 给每个失败定性。
#
#     cd /Users/stephen/DevProjects/AIProjects/elmos
#     bash gate-triage.sh              # 跑全部门禁并分类
#     bash gate-triage.sh --baseline   # 额外跑一遍 main 独跑做差（推荐，见下）
#     bash gate-triage.sh --only ruff-engine,pytest-engine
#
# 与既有 verify-merge.sh 的关系（不是替代品，是它的超集 + 定性）：
#   * 门禁条目：verify-merge.sh 有 10 条，本脚本 14 条，补上 MERGE_NOTES
#     「合完之后要跑的门禁」里它没有的 playwright / operations-scripts-test /
#     production-readiness，以及 business-line-contracts。
#   * verify-merge.sh 跑引擎测试用的是 `pytest -q`。pyproject 的 addopts 已经含 `-q`，
#     再传一次是双 quiet，**摘要计数行整行不打印**，日志没法拿来做差。
#     本脚本一律用 `-o addopts="--strict-markers"` 覆盖。
#   * verify-merge.sh 只报 PASS/FAIL。本仓库的现实是**门禁在 main 上本来就有一片红**，
#     不定性的 FAIL 等于没有信息量 —— 这也是 2026-08-25 一天里四条前提被推翻的原因。
#
# 定性只有四类：
#   MERGE     合并造成的，落地前必须处理
#   PRE-EXIST main 独跑上同样红，与本次合并无关（**不要顺手修**，会把合并 diff 搅浑）
#   ENV       缺工具链 / 缺网 / 缺运行中的服务，机器问题不是代码问题
#   UNKNOWN   没有对上任何已知模式 —— 必须人工看，脚本不替你猜
#
# 退出码 = MERGE + UNKNOWN 的条数。PRE-EXIST 与 ENV 不计入，所以「退出 0」的含义是
# 「这次合并没有引入新问题」，不是「全绿」。
#
# 本脚本不改任何文件；用到的 git 全部是只读且带 GIT_OPTIONAL_LOCKS=0
# （设备桥上的教训：git 的只读命令也会刷索引、留下删不掉的 .git/index.lock）。
# 它自己是临时产物，别提交：请确认 .gitignore 里有 /gate-triage.sh。

set -uo pipefail

# bash 是按文件偏移增量读取脚本的：跑动期间有人编辑本文件，后半段就会解析错乱
# （2026-08-25 真踩过：改了 classify() 上面的行，跑到一半报 syntax error）。
# 所以先把自己复制到 /tmp 再 exec，之后怎么改原文件都不影响这一次跑动。
if [ -z "${GATE_TRIAGE_SNAPSHOT:-}" ]; then
    SELF="/tmp/gate-triage-self.$$.sh"
    cp "$0" "$SELF" || { echo "无法快照自身" >&2; exit 2; }
    GATE_TRIAGE_SNAPSHOT=1 exec bash "$SELF" "$@"
fi

OUT=${GATE_TRIAGE_OUT:-/tmp/gate-triage}
BASE=${GATE_TRIAGE_BASE:-/tmp/gate-triage-baseline}
ENGINE=engines/polyglot-route-engine
DO_BASELINE=0
REUSE=0
BASELINE_REF=""
ONLY=""
PW_INSTALL=0

while [ $# -gt 0 ]; do
    case "$1" in
        --baseline)        DO_BASELINE=1 ;;
        --reuse)           REUSE=1 ;;
        --baseline-ref)    shift; BASELINE_REF="$1"; DO_BASELINE=1 ;;
        --baseline-ref=*)  BASELINE_REF="${1#--baseline-ref=}"; DO_BASELINE=1 ;;
        --only)            shift; ONLY=",$1," ;;
        --only=*)          ONLY=",${1#--only=}," ;;
        --playwright-install) PW_INSTALL=1 ;;
        -h|--help)         sed -n '2,40p' "$0"; exit 0 ;;
        *) echo "未知参数: $1（--help 看用法）" >&2; exit 2 ;;
    esac
    shift
done

[ -e .git ] || { echo "请在仓库根目录运行（elmos 或 elmos-merge 工作树）" >&2; exit 2; }
command -v uv >/dev/null || { echo "找不到 uv" >&2; exit 2; }

if [ "$REUSE" = 1 ]; then
    [ -d "$OUT" ] || { echo "$OUT 里没有上一次的日志，--reuse 无从谈起" >&2; exit 2; }
    echo "reuse：不跑门禁，直接对 $OUT 里已有的日志重新定性"
else
    rm -rf "$OUT"; mkdir -p "$OUT"
fi
touch "$OUT/.start"   # 用来在收尾时查出「跑动期间被改过的文件」

g() { GIT_OPTIONAL_LOCKS=0 git "$@"; }   # 只读 git 一律走这里

echo "仓库:      $(pwd)"
echo "HEAD:      $(g rev-parse --short HEAD 2>/dev/null || echo '?')"
if MH=$(g rev-parse --short MERGE_HEAD 2>/dev/null); then
    echo "MERGE_HEAD: $MH   （合并进行中）"
    echo "未解决冲突: $(g diff --name-only --diff-filter=U 2>/dev/null | wc -l | tr -d ' ') 个文件"
fi
echo "日志:      $OUT/"
echo

# ---------------------------------------------------------------- 门禁定义
# 顺序按「早失败会让后面输出没意义」排：静态 -> 引擎 -> 其它引擎 -> 前端 -> Java -> 自计数校验器
NAMES=(); CMDS=()
add() { NAMES+=("$1"); shift; CMDS+=("$*"); }

add ruff-engine    uv --directory $ENGINE run --locked --group dev ruff check src tests
add mypy-engine    uv --directory $ENGINE run --locked --group dev mypy src
add pytest-engine  uv --directory $ENGINE run --locked --group dev pytest -o 'addopts=--strict-markers' -rf
add pytest-synthesis uv --directory engines/project-synthesis-engine run --locked pytest -o 'addopts=--strict-markers' -rf
add web-console-check pnpm --dir apps/web-console check
add web-console-e2e   pnpm --dir apps/web-console exec playwright test --project=chromium e2e/generation-ui.spec.ts
add mvn-worker     mvn -q -pl apps/java-engine-worker test
add mvn-arch       mvn -q -pl modules/architecture-tests test
add makefile-portability python3 scripts/operations/validate_makefile_portability.py
add operations-scripts-test make operations-scripts-test
add business-line-contracts make business-line-contracts
add production-readiness uv run --quiet --with pyyaml python -m unittest discover -s tests/production-readiness -p 'test_*.py'
add route-matrix   python3 scripts/operations/validate_translation_route_matrix.py
add mature-series  uv run --quiet --with jsonschema==4.25.1 python scripts/validate_mature_product_series.py

if [ "$PW_INSTALL" = 1 ]; then
    echo "==> playwright install chromium（要联网）"
    pnpm --dir apps/web-console exec playwright install chromium || echo "    安装失败，e2e 那条会判 ENV"
    echo
fi

# ---------------------------------------------------------------- 跑
STATUS=()
idx=0
while [ "$idx" -lt "${#NAMES[@]}" ]; do
    name="${NAMES[$idx]}"; cmd="${CMDS[$idx]}"
    idx=$(( idx + 1 ))
    case "$ONLY" in
        "") ;;
        *",$name,"*) ;;
        *) STATUS+=("SKIP"); continue ;;
    esac
    if [ "$REUSE" = 1 ]; then
        if [ -f "$OUT/$name.status" ]; then
            STATUS+=("$(cat "$OUT/$name.status")")
        elif [ -f "$OUT/$name.log" ]; then
            # 上一次没记状态（旧版脚本跑的），只能当失败送去定性
            STATUS+=("FAIL")
        else
            STATUS+=("SKIP")
        fi
        continue
    fi
    printf '\033[1m==> %s\033[0m\n' "$name"
    if eval "$cmd" > "$OUT/$name.log" 2>&1; then
        printf '    PASS\n'; STATUS+=("PASS"); echo PASS > "$OUT/$name.status"
    else
        printf '    FAIL\n'; STATUS+=("FAIL"); echo FAIL > "$OUT/$name.status"
        tail -12 "$OUT/$name.log" | sed 's/^/    | /'
    fi
done

# ---------------------------------------------------------------- 可选：main 独跑基线
# 判据只有一个：同一台机器、同一套命令，main 独跑一遍、合并树一遍，比集合的差。
# 断言「这条红是既有的」而没做这一步，就是今天被推翻四次的那种断言。
BASELINE_OK=0
if [ "$REUSE" = 1 ] && [ -f "$OUT/base-pytest-engine.log" ]; then
    BASELINE_OK=1
    echo "reuse：沿用 $OUT/base-*.log 这份已有基线"
elif [ "$DO_BASELINE" = 1 ]; then
    echo
    # 基线该取哪个 ref，必须说清楚 —— 合并一旦提交，HEAD 就是合并后的树，
    # 再拿 HEAD 当「main 独跑」就是自己跟自己比，差集恒为空，所有问题都会被判成 PRE-EXIST。
    if [ -n "$BASELINE_REF" ]; then
        BREF="$BASELINE_REF"; BWHY="你指定的"
    elif g rev-parse -q --verify MERGE_HEAD >/dev/null 2>&1; then
        BREF=HEAD; BWHY="合并进行中，HEAD 就是被合入的那一侧"
    elif [ "$(g rev-list --parents -n1 HEAD | wc -w | tr -d ' ')" -ge 3 ]; then
        BREF="HEAD^1"; BWHY="HEAD 是合并提交，取第一个父提交"
    else
        BREF=""; BWHY=""
    fi
    if [ -z "$BREF" ]; then
        printf '\033[31m==> 判不出基线该取哪个 ref\033[0m\n'
        echo "    合并已经提交、HEAD 也不是合并提交，拿 HEAD 当基线等于自己跟自己比。"
        echo "    请显式指定，例如：bash gate-triage.sh --baseline-ref c03782bfe"
        DO_BASELINE=0
    fi
fi
if [ "$DO_BASELINE" = 1 ] && [ "$REUSE" != 1 ]; then
    printf '\033[1m==> 构建基线（git archive %s，%s；只读，不碰索引）\033[0m\n' "$BREF" "$BWHY"
    echo "    $(g log -1 --format='%h %s' "$BREF" 2>/dev/null | cut -c1-90)"
    if [ "$(g rev-parse "$BREF" 2>/dev/null)" = "$(g rev-parse HEAD 2>/dev/null)" ]; then
        printf '\033[31m    基线 ref 与 HEAD 是同一个提交 —— 这样比出来的差集恒为空，拒绝继续\033[0m\n'
        DO_BASELINE=0
    fi
fi
if [ "$DO_BASELINE" = 1 ] && [ "$REUSE" != 1 ]; then
    rm -rf "$BASE"; mkdir -p "$BASE"
    if g archive --format=tar "$BREF" | tar x -C "$BASE"; then
        echo "    解到 $BASE"
        ( cd "$BASE" && uv --directory $ENGINE run --locked --group dev \
            ruff check src tests ) > "$OUT/base-ruff-engine.log" 2>&1
        ( cd "$BASE" && uv --directory $ENGINE run --locked --group dev \
            pytest -o 'addopts=--strict-markers' -rf ) > "$OUT/base-pytest-engine.log" 2>&1
        ( cd "$BASE" && uv --directory $ENGINE run --locked --group dev \
            mypy src ) > "$OUT/base-mypy-engine.log" 2>&1
        ( cd "$BASE" && uv run --quiet --with pyyaml python -m unittest discover \
            -s tests/production-readiness -p 'test_*.py' ) > "$OUT/base-production-readiness.log" 2>&1
        BASELINE_OK=1
        echo "    基线 ruff / pytest 跑完"
    else
        echo "    git archive 失败，跳过基线"
    fi
fi

fails_of() { grep '^FAILED ' "$1" 2>/dev/null | awk '{print $2}' | sort -u; }
ruff_of()  { grep -E '^[^ ]+:[0-9]+:[0-9]+: ' "$1" 2>/dev/null | sed 's/:[0-9]*:[0-9]*:/ /' | sort -u; }
# mypy 的行号两侧必然错位，只比 (文件, 错误码, 文本)
mypy_of()  { grep -E '^[^ ]+:[0-9]+: error: ' "$1" 2>/dev/null | sed 's/:[0-9]*: error: / /' | sort -u; }
unit_of()  { grep -E '^(FAIL|ERROR): ' "$1" 2>/dev/null | sort -u; }

if [ "$BASELINE_OK" = 1 ]; then
    echo
    printf '\033[1m===== 与 main 独跑做差 =====\033[0m\n'
    rm -f "$OUT"/*.new    # 清掉上一次留下的差集，否则 reuse 会拿旧结论骗自己
    for pair in "pytest-engine:fails_of" "ruff-engine:ruff_of" "mypy-engine:mypy_of" "production-readiness:unit_of"; do
        gate="${pair%%:*}"; fn="${pair##*:}"
        [ -f "$OUT/$gate.log" ] || continue
        # 没有对应的基线日志就别做差 —— 空集会把既有问题全算成「新增」
        [ -f "$OUT/base-$gate.log" ] || { echo "  [$gate] 没有基线日志，跳过做差"; continue; }
        "$fn" "$OUT/base-$gate.log" > "$OUT/$gate.base.set"
        "$fn" "$OUT/$gate.log"      > "$OUT/$gate.head.set"
        comm -13 "$OUT/$gate.base.set" "$OUT/$gate.head.set" > "$OUT/$gate.new"
        new=$(cat "$OUT/$gate.new")
        gone=$(comm -23 "$OUT/$gate.base.set" "$OUT/$gate.head.set")
        printf '\n  [%s] main 独跑 %s 条 / 合并树 %s 条\n' "$gate" \
            "$(wc -l < "$OUT/$gate.base.set" | tr -d ' ')" \
            "$(wc -l < "$OUT/$gate.head.set" | tr -d ' ')"
        if [ -n "$new" ]; then
            printf '  \033[31m新增（= 合并伤，必须处理）：\033[0m\n'
            echo "$new" | sed 's/^/    + /'
        else
            printf '  新增：无\n'
        fi
        [ -n "$gone" ] && { printf '  被合并修好：\n'; echo "$gone" | sed 's/^/    - /'; }
    done
    echo
    echo "  两侧都在的那些 = PRE-EXIST，别在这次合并里修。"
fi

# ---------------------------------------------------------------- 定性
# 只写「已经有证据的」模式。没对上就是 UNKNOWN，脚本不替你猜。
# 证据出处：M = .ai/MERGE_PERF_VERIFICATION.md，G = 2026-08-25 云端实测（MERGE_NOTES 第八轮）
classify() {
    name="$1"; log="$OUT/$name.log"
    [ -f "$log" ] || { VERDICT=UNKNOWN; WHY="没有日志"; return; }

    if grep -qiE 'command not found|No such file or directory: .?(mvn|pnpm|java)|Unable to locate a Java|Executable doesn.t exist.*playwright|browserType.launch' "$log"; then
        VERDICT=ENV; WHY="缺工具链或缺浏览器（mvn/pnpm/java/playwright）"; return
    fi
    if grep -qE 'MULTIMODAL_ENGINE_UNAVAILABLE|ECONNREFUSED|getaddrinfo|network|ETIMEDOUT' "$log"; then
        VERDICT=ENV; WHY="需要联网或需要一个跑着的服务"; return
    fi
    if grep -qE 'RequireJavaVersion|is not in the allowed range' "$log"; then
        jdk=$(grep -oE 'is version [0-9.]+' "$log" | head -1)
        VERDICT=ENV; WHY="JDK 版本闸：当前 $jdk，enforcer 要 21.x。在仓库根跑 sdk env —— .sdkmanrc 钉的是 java=21.0.6-amzn 与 maven=3.9.10，没装先 sdk env install"; return
    fi
    if grep -q "ModuleNotFoundError: No module named" "$log"; then
        missing=$(grep -o "No module named .*" "$log" | head -1)
        VERDICT=ENV; WHY="缺 Python 依赖（$missing）——这条门禁要用 uv run --with 跑"; return
    fi

    case "$name" in
    ruff-engine)
        # G：合并树 18 条，与 main 独跑的 21 条完全是子集关系（合并净减 F601/F401/F821）。
        n=$(grep -cE '^[^ ]+:[0-9]+:[0-9]+: ' "$log")
        if grep -qE ': (F8[0-9]{2}|F401|F601|F811) ' "$log"; then
            VERDICT=MERGE; WHY="出现 F 类（未定义名/重复定义/未用导入）—— 这类正是嫁接接缝的信号，不是风格问题"
        else
            # 2026-08-25：main 既有的那 18 条已全部修掉，引擎 ruff 基线现在是 0。
            # 所以这里不再有「既有欠账」这一档 —— 出现任何一条都得看。
            VERDICT=UNKNOWN; WHY="$n 条。基线已归零（第八轮补记），任何一条都不是既有欠账"
        fi ;;
    pytest-engine)
        if [ "$BASELINE_OK" = 1 ] && [ -f "$OUT/pytest-engine.new" ]; then
            if [ -s "$OUT/pytest-engine.new" ]; then VERDICT=MERGE; WHY="见上面的差集（新增失败）"
            else VERDICT=PRE-EXIST; WHY="相对 main 独跑没有新增失败（见上面的差集）"; fi
        elif grep -q 'PIPELINE_NO_VERIFIED_UNITS' "$log" && ! grep -q 'native' "$log"; then
            VERDICT=ENV; WHY="没有 passed unit ⇒ 守卫先抛，被测的错误码走不到（G）。装齐 analyzer 再看"
        else
            VERDICT=UNKNOWN; WHY="没跑基线就判不了。加 --baseline 重跑"
        fi ;;
    mypy-engine)
        if [ "$BASELINE_OK" = 1 ] && [ -f "$OUT/mypy-engine.new" ]; then
            if [ -s "$OUT/mypy-engine.new" ]; then VERDICT=MERGE; WHY="见上面的差集（新增类型错误）"
            else VERDICT=PRE-EXIST; WHY="相对 main 独跑没有新增类型错误"; fi
        else
            VERDICT=UNKNOWN; WHY="没跑基线就判不了。加 --baseline 重跑"
        fi ;;
    web-console-check)
        if grep -q 'exact_versions' "$log"; then
            VERDICT=PRE-EXIST; WHY="routes/inventory.json 缺 exact_versions —— c03782bfe 加了必填字段却没填数据，与本次合并无关（M）"
        else VERDICT=UNKNOWN; WHY="11 条 script 里哪条挂了，看日志"; fi ;;
    business-line-contracts)
        if grep -q 'V3_REPOSITORY_STATUS_DRIFT' "$log"; then
            VERDICT=PRE-EXIST; WHY="V3_REPOSITORY_STATUS_DRIFT，是另一笔未完成的编辑（M）"
        else VERDICT=UNKNOWN; WHY="换了失败点，看日志"; fi ;;
    route-matrix)
        if grep -q 'V3_REPOSITORY_STATUS_DRIFT' "$log"; then
            VERDICT=PRE-EXIST; WHY="V3_REPOSITORY_STATUS_DRIFT —— 另一笔未完成的编辑，卡在算路线条数之前（M）"
        else
            VERDICT=MERGE; WHY="自计数校验器：输出直接给出该写进 README / BUSINESS_LINE_CLOSURE_MATRIX 的数字（规则 8）"
        fi ;;
    mature-series|makefile-portability)
        VERDICT=MERGE; WHY="自计数校验器：输出直接给出该写回文档的数字（规则 8）" ;;
    production-readiness)
        if grep -q 'skill_inventory_ui_matches_callable_repository_directories' "$log"; then
            VERDICT=UNKNOWN; WHY="Skill 目录数与 UI 里写死的数字对不上（如 1847 != 1267）。加 --baseline 才能判是不是既有漂移"
        else
            VERDICT=UNKNOWN; WHY="看日志"
        fi ;;
    web-console-e2e)
        VERDICT=UNKNOWN; WHY="playwright.config.ts 的就绪 URL 只能靠这条验；指错会挂起而不是报错，先看是超时还是断言" ;;
    *)  VERDICT=UNKNOWN; WHY="没有已知模式" ;;
    esac
}

echo
printf '\033[1m===== 汇总 =====\033[0m\n'
bad=0; skipped=0; idx=0
while [ "$idx" -lt "${#NAMES[@]}" ]; do
    name="${NAMES[$idx]}"; st="${STATUS[$idx]:-SKIP}"; idx=$(( idx + 1 ))
    case "$st" in
        PASS) printf '  \033[32m%-24s PASS\033[0m\n' "$name"; continue ;;
        SKIP) printf '  %-24s SKIP\n' "$name"; skipped=$(( skipped + 1 )); continue ;;
    esac
    classify "$name"
    case "$VERDICT" in
        MERGE)     color=31; bad=$(( bad + 1 )) ;;
        UNKNOWN)   color=33; bad=$(( bad + 1 )) ;;
        *)         color=90 ;;
    esac
    printf '  \033[%sm%-24s FAIL  %-10s %s\033[0m\n' "$color" "$name" "$VERDICT" "$WHY"
done

echo
touched=$(find "$ENGINE/src" "$ENGINE/tests" -type f -newer "$OUT/.start" 2>/dev/null | grep -v __pycache__ | head -20)
if [ -n "$touched" ]; then
    printf '\033[33m⚠ 这次跑动期间有文件被改过（并发会话或你自己）——上面的结果是混合树的，请重跑：\033[0m\n'
    echo "$touched" | sed 's/^/    /'
    echo
fi
printf '需要处理的（MERGE + UNKNOWN）：%d 条；跳过 %d 条。全部日志在 %s/\n' "$bad" "$skipped" "$OUT"
if [ "$REUSE" = 1 ]; then
    echo "提示：reuse 模式没有重跑任何门禁，PASS/FAIL 来自上一次；旧版脚本留下的日志没有状态文件，会一律按 FAIL 送去定性。"
fi
if [ "$BASELINE_OK" != 1 ]; then
    echo "提示：没跑 --baseline，pytest 的定性只能靠模式猜。要下结论请加 --baseline 重跑一次。"
fi
if [ "$bad" -eq 0 ] && [ "$skipped" -eq 0 ]; then
    cat <<'TXT'

这次合并没有引入新问题。落地前仍有三件事（MERGE_NOTES）：
  1. ELMOS_INTEGRATION_MANIFEST.json 的计数与 sha256 要重新生成（现为占位）
  2. README 与 BUSINESS_LINE_CLOSURE_MATRIX 的路线条数，按 route-matrix 的输出改
  3. validate_mature_product_series 的 schema 计数，按它的输出改
TXT
fi
exit "$bad"
