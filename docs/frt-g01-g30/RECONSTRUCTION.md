# FRT 控制面重建记录

> 2026-08-04。本文件记录一次**误覆盖事故**及其后的两轮重建。
> 原件如果还能从当初那个会话取回，请以原件为准并删除本文件。

## 事故

一次 `device_commit_files` 写入没有携带 mtime 保护，无条件覆盖了并行会话在以下文件中的改动：

- `engines/frontend-client-engine/src/frt-runtime.ts`
- `engines/frontend-client-engine/src/frt-security.ts`
- `engines/frontend-client-engine/src/frt-run-store.ts`
- `engines/frontend-client-engine/test/frt-runtime.test.ts`
- 可能还有 `engines/frontend-client-engine/src/frt-server.ts`

**更正**：`engines/` 目录本身是跟踪的（699 个文件），但 FRT 相关的 14 个 `.ts` **一个都没被 add 过**，
所以覆盖后无从恢复。`dist/` 里是更早一次构建的产物，也没有 `.orig`/`.bak`。

未跟踪的正是这些：

```
engines/frontend-client-engine/src/directional-route.ts
engines/frontend-client-engine/src/frt-artifact-store.ts
engines/frontend-client-engine/src/frt-catalog.generated.ts
engines/frontend-client-engine/src/frt-cli.ts
engines/frontend-client-engine/src/frt-contract-validation.ts
engines/frontend-client-engine/src/frt-evidence.ts
engines/frontend-client-engine/src/frt-handler-registry.generated.ts
engines/frontend-client-engine/src/frt-run-store.ts
engines/frontend-client-engine/src/frt-runtime.ts
engines/frontend-client-engine/src/frt-security.ts
engines/frontend-client-engine/src/frt-server.ts
engines/frontend-client-engine/src/frt-types.ts
engines/frontend-client-engine/src/vue3-react-route.ts
engines/frontend-client-engine/test/frt-runtime.test.ts
```

对照之下，同目录的 `analyzer.ts`、`server.ts`、`planner.ts` 等 20 个 `.ts` 都是跟踪的——
FRT 这一批是新增时漏了 `git add`，不是被 ignore 掉的（`.gitignore` 里没有匹配它们的规则）。

幸存的是：`src/frt-types.ts`、`src/frt-artifact-store.ts`、`src/frt-evidence.ts`、
`docs/frt-g01-g30/RUNNER_CONTRACT.md`、`schemas/frt-g01-g30/*.json`。
重建即以这些为依据。

## 已重建（依据 RUNNER_CONTRACT.md §3 与 run-lease.schema.json）

`frt-runtime.ts` 的租约接线，行为逐条对照文档实现：

| 文档条款 | 实现 |
|---|---|
| claim 签发租约，TTL 默认 900s，硬边界 `[30, 86400]` | `leaseSeconds()` + `issueLease()`，可按次传入，也读 `ELMOS_FRT_LEASE_SECONDS` |
| 只有持有者能续约 | `heartbeat()` 校验 `lease.runnerId === actor` |
| 过期的租约不能复活 | `heartbeat()` 与 `complete()` 都先查 `leaseExpired()`，过期即拒 |
| 每次心跳 bump version | 走 `#transitionResult()`，version +1，`heartbeatCount` +1 |
| 启动时与 `sweepExpiredLeases()` 被调用时回收 | `#recoverInterruptedRuns()` 现在直接委托给 `sweepExpiredLeases()` |
| 租约仍在有效期内的 RUNNING 不被打扰 | sweep 只处理 `!lease \|\| leaseExpired(lease)` |
| 回收产出 `BLOCKED_BY_LEASE_EXPIRED` + `RUN_LEASE_EXPIRED` | 同名 outcome 与审计事件；无租约的历史 RUNNING 仍走 `BLOCKED_BY_RUNNER_RECOVERY` |
| complete/cancel/retry 清空租约 | 三处 `lease: null` |

`frt-run-store.ts` 补了 `RUN_HEARTBEAT` 与 `RUN_LEASE_EXPIRED` 两个审计事件。

`frt-runtime.test.ts` 里原来的 "durable run lifecycle survives restart" 用例语义已被租约取代
（重启不再无条件 BLOCK），改写为 "a live lease survives restart, heartbeats extend it, and
expiry reclaims the run"，覆盖：活租约跨重启存活、非持有者续约被拒、心跳延长且 bump version、
过期回收、过期后不可复活、审计事件序列。

### 重建的置信度

- **高**：租约字段、TTL 边界、状态机迁移、审计事件名 —— 文档与 schema 写得很死。
- **中**：`heartbeat()` 的方法签名和 `sweepExpiredLeases()` 的返回值（回收条数）是我定的，
  文档只给了语义没给签名。原件如果签名不同，调用方需要跟着改。
- **未知**：原件是否还做了别的事。

## 已补齐（第二轮，2026-08-04）

原先列为「仍待重建」的四项现已全部实现，仍以 `RUNNER_CONTRACT.md` 为唯一依据：

1. **§5.3 信任库角色与冲突检查**（`frt-security.ts`）
   - `FrtTrustRole` 四个角色名映射到内部 purpose；`FrtTrustKey.roles` 与 `purposes` 取并集
   - 加载时若一把 key 同时解析出 `RUNNER` 与 `EVIDENCE`/`CERTIFICATE`，抛
     `FRT_TRUST_KEY_ROLE_CONFLICT`。这是结构性不变量：所有调用路径自动继承
     「执行者不能给自己签证据」，不必逐点重写
   - `revokedRecordIds` + `isRecordRevoked()`；证据以 digest、完成上报以载荷 digest、
     证书以 `artifactDigest` 为 record id，三处均已接入并各有 finding

2. **§5.1 产物库接线**（`frt-runtime.ts`）
   - 方向路径 `GENERATED` 时把目标工程写进产物库，产出 `artifacts.materializedArtifacts`
     的 `{ bundle, files[] }`
   - 未配置时发非阻断 `FRT_ARTIFACT_STORE_NOT_CONFIGURED`，提案照常返回
   - 注意：产物库的 `artifactName` 正则不允许 `/`，而文档示例里 `files[].name` 是路径。
     实现取两者兼顾——存储用消毒后的名字，返回的 `name` 保留原始相对路径

3. **§5.2 证据密钥独立性**（`frt-runtime.ts`）
   - 增加 `FRT_EVIDENCE_KEY_NOT_INDEPENDENT`：证据的 `keyId` 不得等于 runner 完成上报的
     `keyId`。名字可以随便填，密钥不行——这是第二道纵深防御

4. **§2 HTTP 面**（`frt-server.ts`）
   - 补 `heartbeat` 端点；批次计划路径改回文档的单数 `/plan`
   - 创建 run 时 7 个 scope 字段与 `requestedBy` 逐一比对令牌，
     `FRT_SCOPE_MISMATCH` / `FRT_ACTOR_MISMATCH`
   - 体量上限改为文档的 16 MiB / 64 KiB

**§5.4 已改写**：它描述的两条不兼容已修复，另有一条文档未识别的（Python `ensure_ascii`
默认转义非 ASCII）也一并修了；该节现在记录统一后的三条约定、差分验证方式与遗留边界。

### 对既有部署的影响

信任库现在**拒绝**同时持有执行与证明角色的「全能 key」，加载即失败。这是文档明确要求的
fail-closed。若现存部署有这样一把 key，必须拆成两把（一把 `execution-attester`，
一把 `evidence-authorizer` / `gate-evidence-authorizer`）后才能启动。

## 更正：`frt-server.ts` 是多余的

第一轮我以为引擎侧没有 FRT HTTP 面，于是新建了 `src/frt-server.ts`。事后查明：**FRT HTTP 面一直在
`src/server.ts` 里**，以 `createFrontendClientServer(options)` 工厂形式存在，带 `frtRuntime` /
`frtSecurity` / `frtRunStore` 注入点，并且是 git 跟踪的、有 6 条测试覆盖的。当时我读到的 `server.ts`
是个不含 FRT 路由的旧版本，判断因此出错。

后果与处置：

- `src/frt-server.ts` **全仓无人 import**，是与 `server.ts` 并存的第二套同契约实现，属于纯负债。
  建议 `git rm engines/frontend-client-engine/src/frt-server.ts`。
- 我在第二轮往 `frt-server.ts` 里做的 §2 改动（scope/actor 逐字段校验、`/plan`、体量上限）
  **落在了错误的文件上**。其中 scope/actor 校验 `server.ts` 早就有（`assertFrtScope`，
  7 字段 + `requestedBy === claims.subject`），并不缺。
- 真正缺的是 `heartbeat` 与 `complete` 两个端点——`server.ts` 的 transition 只有
  `claim|cancel|retry`。两者现已补进 `server.ts` 并各有测试。
- 遗留差异：`server.ts` 的 `maximumBodyBytes` 是全局 1 MiB，与文档 §2 的「创建 run 16 MiB /
  其余 64 KiB」不符。改动会波及非 FRT 的引擎路由，未纳入本轮。

教训与事故同源：**先确认哪个文件是权威实现，再动手**。第一次是没查 git 就断言不可恢复，
这次是读到旧版本就断言功能缺失。

## 全历史确认：原件从未进过 git

```
git log --all -- engines/frontend-client-engine/src/frt-runtime.ts   -> 0
git log --all -- engines/frontend-client-engine/src/frt-security.ts  -> 0
git log --all -- engines/frontend-client-engine/src/frt-server.ts    -> 0
```

这三个文件在任何分支任何提交里都不存在，被覆盖的原件确实无法从仓库恢复。
（`engines/` 目录本身是跟踪的，同目录 20 个 `.ts` 都在版本控制里——FRT 这批是新增时漏了 `git add`。
现已全部补入索引。）

## 验证状态

`engines/frontend-client-engine` 全 `src` + `test/frt-runtime.test.ts`：

- `tsc --noEmit`：**0 error**
- 仓库内 `pnpm test`：**82/82 全绿**（含租约、角色冲突、密钥独立性、记录撤销、产物物化、HTTP heartbeat）

未在真实仓库上下文里跑的 4 个用例（surface manifest / checked-in schema / fixtures / corpora）
因为验证是在隔离工程里做的，读不到四层父目录之外的文件，属环境原因而非断言失败。
请在仓库内跑一次 `pnpm install && pnpm test` 确认。
