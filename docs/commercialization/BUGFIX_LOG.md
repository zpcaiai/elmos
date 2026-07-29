# 商业化制品缺陷修复记录

日期：2026-07-28
范围：本轮商业化工作自身产出的制品（`deploy/production/**`、`scripts/**`）
说明：本记录只覆盖**本轮新增制品**的缺陷。仓库既有代码未在本轮改动，
也未在本环境构建过（无 Java/Node 工具链）。

---

## B1 · 生产编排的内部网络会切断全部出站流量 ★ 严重

**文件**：`deploy/production/compose/docker-compose.production.yml`

**症状**：网络定义写成

```yaml
internal:
  driver: bridge
  internal: true
```

Docker 的 `internal: true` 会切断该网络上所有容器的出站流量。而挂在这张网上的
`control-plane`、`commercial-api`、`workspace-service` 必须访问：

- 托管 PostgreSQL（外部主机）
- 支付宝 / 微信支付 API 与回调重试
- Runner Agent（独立主机）

**后果**：容器能起来，但首次连库即失败。症状表现为"连不上数据库"，
排查时很难第一时间联想到是 compose 的网络定义。这是那种**部署当天才会炸、
且指向错误方向**的缺陷。

**修复**：网络改名 `backend` 并去掉 `internal: true`。出网限制交给
宿主防火墙 + `egress-proxy` 白名单，而不是一刀切。原因写进文件注释，避免被"优化"回去。

**验证**：YAML 解析通过；断言全部 8 个服务不再挂 internal 网络。

---

## B2 · MinIO 健康检查依赖镜像不保证存在的客户端

**文件**：同上

**症状**：`test: ["CMD", "mc", "ready", "local"]`。`mc` 是独立的 MinIO 客户端，
服务端镜像不保证包含。

**后果**：健康检查恒失败 → 容器被判 unhealthy → 依赖它的服务无法正常启动或被反复重启。

**修复**：改用官方健康端点 `curl -fsS http://127.0.0.1:9000/minio/health/live`。

---

## B3 · 告警规则引用了 5 个不存在的指标 ★ 隐蔽

**文件**：`deploy/production/observability/prometheus-rules.yml`

**症状**：`promtool` 校验通过（语法没问题），但下列指标当前没有任何产生方：

```
elmos_service_readiness
elmos_runner_token_expires_at_seconds
elmos_billing_reserved_lease_age_seconds_max
elmos_backup_last_success_timestamp_seconds
elmos_restore_drill_last_success_timestamp_seconds
```

**后果**：**无数据的告警不会触发，等于没有告警**，但看板上显示"已配置 12 条告警"。
这比没配告警更危险——它制造了被监控的错觉。备份告警尤其致命：
备份停了三个月也不会有人知道。

**修复**：

1. 文件头明确区分【已埋点】与【需先埋点】两类指标
2. 新增 `elmos-meta` 组，用 `absent()` 监控指标本身是否存在：
   `BillingMetricsAbsent` / `BackupMetricAbsent` / `RunnerTokenMetricAbsent`

**验证**：`promtool check rules` → SUCCESS: 15 rules found。

---

## B4 · 环境变量模板混淆"已生效"与"尚未实现"

**文件**：`deploy/production/elmos-commercial.env.example`

**症状**：按 D-01 新增的 `ELMOS_PAYMENT_PROVIDER`、支付宝/微信全部变量，
与既有变量混排且同样标 `[REQUIRED]`。

**后果**：运维会以为填上就能收款，实际上适配器还没写，填了也不会生效。

**修复**：新增 `[NEW]` 与 `[DISABLED]` 两个状态标记，并在图例中说明
"填了也不会生效，直到对应实现落地"。Stripe 六项标 `[DISABLED]`。
校验脚本确认 **74 个变量全部有明确状态归属**。

---

## B5 · 定价门禁遇到畸形目录会抛栈回溯

**文件**：`scripts/commercial/validate_pricing_catalog_publication.py`

**症状**：`plans` 数组里混入非对象元素时：

```
AttributeError: 'str' object has no attribute 'get'
```

**后果**：**门禁脚本自己崩掉等于没有门禁**。畸形输入应当得到明确的 `INVALID` 判定，
而不是一段栈回溯——后者在 CI 里会被当成"脚本坏了"，而不是"目录有问题"。

**修复**：

1. 逐项确认 `plans` 元素是对象，不是则给出 `plans 中第 [n] 项不是对象` 并返回
2. 补齐 `tokenClasses` / `creditRates` / `limitations` 的存在性检查（Schema 要求但原先漏检）

**验证**：12 个用例全部通过，含两个新增的畸形输入用例。

---

## B6 · Runner 预置脚本三处健壮性与可移植性缺陷

**文件**：`scripts/operations/provision_runner_host.sh`

### B6-a：`set -u` 下非数字内容导致脚本崩溃

```bash
ns="$(cat /proc/sys/user/max_user_namespaces)"
if [[ "$ns" -gt 0 ]]; then ...
```

在 `[[ -gt ]]` 中，非数字字符串会被当作**变量名**求值。配合 `set -u`，
结果是 `bash: abc: unbound variable`，脚本以退出码 1 中止——
而 1 并不在这个脚本的语义里（3=未就绪，4=拒绝）。调用方会误判。

**修复**：先用 `[[ "$ns" =~ ^[0-9]+$ ]]` 确认是纯数字，否则给出 `[MISS]` 并计入未就绪。
**验证**：注入 `abc` 后退出码为 3，无 stderr 输出。

### B6-b：`--apply` 未校验平台

`useradd` / `usermod --add-subuids` 是 Linux 专有。在 macOS 上执行会以
难以理解的方式失败。

**修复**：`--apply` 前置断言 `uname -s == Linux`，并逐个校验
`useradd` / `usermod` / `install` 存在，否则以退出码 4 明确拒绝。

### B6-c：`nologin` 路径写死

`/usr/sbin/nologin` 是 Debian 系路径，RHEL 系在 `/sbin/nologin`。

**修复**：按 `/usr/sbin/nologin` → `/sbin/nologin` → `/bin/false` 依次探测。

---

## 修复后的完整回归

| 检查 | 结果 |
|---|---|
| `docker-compose.production.yml` YAML 解析 + 网络断言 | PASS |
| `promtool check rules` | SUCCESS: 15 rules found |
| `bash -n provision_runner_host.sh` | PASS |
| `provision_runner_host.sh --check`（无配置） | exit 3 |
| `provision_runner_host.sh --check`（危险根 `/`） | exit 4 |
| `provision_runner_host.sh`（`max_user_namespaces` 异常） | exit 3，不再崩溃 |
| 定价门禁 12 用例 | 全部 PASS |
| 单位经济性工具 7 用例 | 全部 PASS |
| 环境变量状态标注覆盖 | 74/74 |

---

## 仍未验证的部分（不要误读为已修复）

- `docker-compose.production.yml` **从未 `up` 过**。`read_only` 与 `user` 标记
  VERIFY-REQUIRED 的项依赖各镜像的实际写入路径，本环境无法构建镜像。
- 告警规则**从未对接真实指标源**，没有任何一条被真实触发或恢复验证过。
- `provision_runner_host.sh --apply` **从未在真实 Runner 主机执行**。
- 仓库既有的 Java / TypeScript / Python 代码**本轮未做任何改动，也未构建**。
  如需在这些代码里查 bug，需要能跑 `mvn` / `pnpm` / `uv` 的环境。
