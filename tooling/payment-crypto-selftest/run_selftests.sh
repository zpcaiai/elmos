#!/usr/bin/env bash
# 编译并运行支付链路的全部自检。
#
# 这些自检不是 JUnit，也不在 mvn 生命周期里 —— 它们刻意独立，
# 因为其中几项需要真实的 Spring / 真实的 PostgreSQL / 真实的扫描器，
# 而不是替身。跑它们只需要 JDK 21 与一个已构建的 fat jar。
#
# 依赖从 apps/commercial-api/target/*-exec.jar 的 BOOT-INF/lib 里取，
# 不需要联网、不需要 Maven Central。所以必须先构建过一次：
#
#     mvn -pl apps/commercial-api -am package -DskipTests
#
# 用法（仓库根目录）：
#     bash tooling/payment-crypto-selftest/run_selftests.sh
#
# 退出码：0 全通过 / 1 有失败 / 3 前置条件不满足（NOT_RUN，不等于通过）

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

EXEC_JAR="$(ls apps/commercial-api/target/*-exec.jar 2>/dev/null | head -1)"
APP_JAR="$(ls apps/commercial-api/target/*.jar 2>/dev/null | grep -v exec | head -1)"

if [ -z "$EXEC_JAR" ] || [ -z "$APP_JAR" ]; then
    echo "NOT_RUN: 找不到已构建的 jar。先跑一次："
    echo "         mvn -pl apps/commercial-api -am package -DskipTests"
    echo "         这不等于通过。"
    exit 3
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "== 从 $EXEC_JAR 取依赖 =="
(cd "$WORK" && unzip -q -o "$ROOT/$EXEC_JAR" 'BOOT-INF/lib/*')
LIB="$WORK/BOOT-INF/lib"
CP="$LIB/*:$ROOT/$APP_JAR"

echo "== 编译被测代码 =="
SRC="$WORK/src"
mkdir -p "$SRC"
javac -encoding UTF-8 -nowarn -cp "$CP" -d "$SRC" \
    apps/commercial-api/src/main/java/io/elmos/commercialadapter/payment/*.java \
    apps/commercial-api/src/main/java/io/elmos/commercialapi/*.java 2>&1 | grep -v '^Note:' || true
if [ ! -d "$SRC/io" ]; then
    echo "编译失败，中止。"
    exit 1
fi

echo "== 编译自检 =="
javac -encoding UTF-8 -nowarn -cp "$SRC:$CP" -d "$SRC" \
    tooling/payment-crypto-selftest/*.java 2>&1 | grep -v '^Note:' || true

# 结账分流自检要跑两遍：一遍用仓库里的真实目录（DRAFT，验"门关着"），
# 一遍用一份状态位改成已配置的目录（验门开之后的分流逻辑）。
# 目录是 static final 一次性加载，所以必须是两个 JVM。
PUBLISHED="$WORK/published"
mkdir -p "$PUBLISHED/pricing"
python3 - "$PUBLISHED/pricing/elmos-cny-self-serve-v1.json" <<'PY'
import json, sys
source = "contracts/pricing-catalog-schema/elmos-cny-self-serve-v1.json"
catalog = json.load(open(source, encoding="utf-8"))
# catalogVersion 保持不变 —— 改了它 PricingPlanCatalog 加载时就会拒绝
catalog["status"] = "PUBLISHED"
catalog["sellerLegalEntityStatus"] = "CONFIGURED"
catalog["taxStatus"] = "CONFIGURED"
catalog["paymentStatus"] = "CONFIGURED"
catalog["costValidationStatus"] = "VALIDATED"
json.dump(catalog, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PY

failures=0
run() {
    local label="$1"; shift
    local extra_cp="${1:-}"; shift || true
    local class="$1"
    local prefix="$SRC:$CP"
    [ -n "$extra_cp" ] && prefix="$extra_cp:$prefix"
    local output
    output="$(java -Dstdout.encoding=UTF-8 -cp "$prefix" "$class" 2>&1 \
              | grep -vE '^[0-9]{2}:[0-9]{2}:[0-9]{2}' | grep -v 'WARN org')"
    local code=$?
    printf '%-34s %s\n' "$label" "$(echo "$output" | tail -1)"
    if [ $code -ne 0 ]; then
        failures=$((failures + 1))
        echo "$output" | grep -E '\[FAIL\]' | head -10
    fi
}

echo
echo "== 运行 =="
run "支付加解密"            "" PaymentCryptoSelfTest
run "下单网关"              "" CheckoutGatewaySelfTest
run "回调端口 SQL"          "" JdbcPortsSelfTest
run "订单端口 SQL"          "" OrderPortsSelfTest
run "重放时间窗"            "" ReplayGuardSelfTest
run "回调管线顺序"          "" PaymentPipelineSelfTest
run "回调适配器（真实密钥）" "" CallbackAdapterSelfTest
run "定价目录契约"          "" CatalogContractSelfTest
run "Spring 装配"           "" SpringWiringSelfTest
run "Security 过滤器链"     "" io.elmos.commercialapi.SecurityFilterChainSelfTest
run "结账分流（DRAFT 目录）" "" io.elmos.commercialapi.CheckoutRoutingSelfTest
run "结账分流（已发布目录）" "$PUBLISHED" io.elmos.commercialapi.CheckoutRoutingSelfTest

echo
if [ $failures -eq 0 ]; then
    echo "全部通过。"
else
    echo "$failures 组有失败。"
    exit 1
fi
