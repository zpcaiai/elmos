# FRT G01–G30 缺口清单

> 生成日期：2026-08-04　·　对象仓库：`elmos`　·　包版本：`FRT_G01_G30_Complete_Skills_Pack`（472 Skill / 30 Batch / 30 有向路径）
> 事实来源：`docs/frt-g01-g30/installed-manifest.json`、`engines/frontend-client-engine/src/frt-runtime.ts`、`frt-catalog.generated.ts`、`frt-handler-registry.generated.ts`、`directional-route.ts`

## 0. 一句话结论

规范层 100% 完成，治理运行时约 80% 完成，**真实转换功能 82/472（17.4%）**，端到端认证 **0/472**。
主要瓶颈不是 handler 代码不够，而是 **没有 external runner**——390 个兜底 Skill 里有 192 个（49%）即使写完 handler 也无法产出证据。

| 指标 | 数值 | 依据 |
|---|---|---|
| Batch | 30/30 规范齐备 | `frt-catalog.generated.ts` |
| Skill | 472 全部注册 | `frt-handler-registry.generated.ts`（10,859 行，全部为元数据） |
| 有真实 handler 的 Skill | **82** | `frt-runtime.ts` `analysisArtifacts()` 的 5 个分支 |
| 落入兜底分支的 Skill | **390** | 同上，`return` 兜底对象，含 `externalExecution: "NOT_RUN"` |
| surface 目录 | 2,360 个 | 每个只有 `surface-manifest.json`，**0 个实现文件** |
| surface 状态 | 2,360/2,360 = `shared_implementation` | 全部指向同一套共享引擎 |
| 证书状态 | 472/472 = `NOT_CERTIFIED` | `installed-manifest.json` |
| 30 条路径证据 | 30/30 `sourceBuild`=`targetBuild`=`browserOrDeviceEvidence`=`NOT_RUN` | `frt-catalog.generated.ts` routes |

## 1. 判定口径

一个 Skill 记为「有真实 handler」，当且仅当它的 `handler_kind` 命中 `frt-runtime.ts` `analysisArtifacts()` 里的具体分支：

| handler_kind | 实际调用 | 行为 |
|---|---|---|
| `estate_discovery` / `semantic_ir` / `typed_contract` | `analyzer.ts` → `discoverWorkspace()` + `buildUiSemanticGraph()`（181 行） | 真实解析源文件，产出 inventory + UI 语义图 |
| `migration_planning` | `planner.ts` → `planFrontendMigration()`（85 行） | 真实产出迁移计划 |
| `directional_route` | `directional-route.ts` → `convertDirectionalRoute()`（717 行）；`FRT-1305` 走 `vue3-react-route.ts`（376 行） | 由 Portable UI IR 生成六种目标栈骨架 |

其余 18 类全部落到函数末尾的兜底 `return`，只回显：`handlerKind`、`action`、输入键名、快照摘要、策略版本，外加常量 `externalExecution: "NOT_RUN"`，以及一份由 `SKILL.md` 元数据编译出的 `compiledContract`。**没有任何领域计算。**

兜底档位定义：

- **A 档（静态可实现，155 个）**：handler 内即可算出结论，不依赖外部执行环境。
- **B 档（需外部工具或产品自身，43 个）**：需要 prover / SMT / model checker，或需要先把 SDK、Registry、Console、Durable Job 这些产品件本身做出来。
- **C 档（必须真实执行环境，192 个）**：结论只能来自真实旅程、真实压测、真实混沌、真实渗透、真实生产观测——**强依赖 external runner**。

## 2. G01–G30 逐批缺口

| 批次 | 主题 | 证书族 | Skill 数 | 有真实 handler | 兜底 | 兜底 handler_kind | 兜底档位 |
|---|---|---|---|---|---|---|---|
| G01 | 系统宪章、Monorepo、Skill标准、Artifact与Release Gate基础 | FD | 12 | 0 | 12 | `governance`×12 | A |
| G02 | Repository Discovery、技术识别、依赖图与可迁移仓库模型 | RM | 13 | **13** `analyzer.ts` | 0 | — | — |
| G03 | Typed Semantic IR与Universal Semantic Type System | IR | 13 | **13** `analyzer.ts` | 0 | — | — |
| G04 | Vue2、Vue3、React、小程序、ArkUI、Flutter六类Source Adapter | SA | 13 | **13** `analyzer.ts` | 0 | — | — |
| G05 | Semantic Gap、兼容性评估、Product Decision与Migration Plan | MP | 13 | **13** `planner.ts` | 0 | — | — |
| G06 | 六类Target Architecture Synthesizer与可构建Skeleton | TA | 13 | 0 | 13 | `source_generation`×13 | A |
| G07 | Code Generation Kernel、AST Emitter、Typed Hole与确定性修复 | CG | 15 | 0 | 15 | `build_toolchain`×15 | A |
| G08 | Component、Props、Events、Slots、Hooks、Context与Identity语义 | CS | 13 | 0 | 13 | `test_automation`×13 | A |
| G09 | State、Effect、Lifecycle、Concurrency、Cancellation与Resource语义 | RS | 14 | 0 | 14 | `delivery_pipeline`×14 | A |
| G10 | Routes、Forms、Network、Storage、Identity与Permissions边界 | AB | 14 | 0 | 14 | `design_system`×14 | A |
| G11 | UI、Layout、Style、Assets、i18n与Accessibility语义 | UI | 14 | 0 | 14 | `mobile_client`×14 | A |
| G12 | 平台能力、Native Bridge、支付、权限与Device Fake | CP | 14 | 0 | 14 | `cross_platform`×14 | A |
| G13 | Vue2、Vue3、React Web Triangle六条有向转换路径 | WR | 11 | **6** `directional-route.ts` | 5 | `route_orchestration`×5 | A |
| G14 | Web与微信小程序双向六条转换路径 | WM | 12 | **6** `directional-route.ts` | 6 | `route_orchestration`×6 | A |
| G15 | Web与ArkUI双向六条转换路径 | WA | 12 | **6** `directional-route.ts` | 6 | `route_orchestration`×6 | A |
| G16 | Web与Flutter双向六条转换路径 | WF | 12 | **6** `directional-route.ts` | 6 | `route_orchestration`×6 | A |
| G17 | 小程序、ArkUI、Flutter Mobile Triangle六条有向路径与30路径收口 | TR | 14 | **6** `directional-route.ts` | 8 | `route_orchestration`×8 | A |
| G18 | Domain、Framework、UI、State、Router、Build、Version、Enterprise与Industry Packs | PK | 15 | 0 | 15 | `compatibility`×15 | A |
| G19 | Proof Obligation、Lean、SMT、Model Checking、CEGAR与反例驱动修复 | FA | 19 | 0 | 19 | `advanced_verification`×19 | B |
| G20 | Skill SDK、Runtime、Registry、Marketplace、Worker与一键产品化 | PD | 24 | 0 | 24 | `runtime_operations`×24 | B |
| G21 | Requirements Traceability 与全系统功能闭环 | — | 12 | 0 | 12 | `product_workflow`×12 | C |
| G22 | 端到端价值流、业务状态机、Saga、补偿、对账与业务线闭环 | — | 19 | 0 | 19 | `product_workflow`×19 | C |
| G23 | Data Contract、全链路血缘、数据Authority、一致性、修复与生命周期闭环 | — | 16 | 0 | 16 | `product_workflow`×16 | C |
| G24 | 管理端能力矩阵、运营治理、异常处置、数据修正与全后台闭环 | — | 20 | 0 | 20 | `administration`×20 | C |
| G25 | 任务可完成性、全旅程可用性、无障碍、多端适配与感知性能 | — | 18 | 0 | 18 | `product_workflow`×18 | C |
| G26 | 全量回归测试、并行测试平台、Flaky治理与Release Qualification | — | 20 | 0 | 20 | `product_workflow`×20 | C |
| G27 | 高并发正确性、性能容量、压力稳定性与安全降级 | — | 20 | 0 | 20 | `performance_capacity`×20 | C |
| G28 | 高可用、故障隔离、Chaos、灾难恢复与持续韧性认证 | — | 20 | 0 | 20 | `resilience_dr`×20 | C |
| G29 | 威胁建模、身份权限、供应链、AI安全、隐私合规与持续安全认证 | — | 23 | 0 | 23 | `security_privacy`×23 | C |
| G30 | Production Readiness、SRE运营、渐进发布、自动回滚与持续认证总收口 | — | 24 | 0 | 24 | `production_readiness`×24 | C |
| **合计** | | | **472** | **82** | **390** | 18 类 | A=155 B=43 C=192 |
### 逐批要点

- **G02–G05（52 个，全绿）**：唯一四个 handler 完整的批次。但注意 `analyzer.ts` 只有 181 行、`planner.ts` 只有 85 行，覆盖深度对照 `SKILL.md` 里声明的 13 项职责仍有差距——属于「有真实实现但未做深」，不在 390 之列。
- **G13–G17（61 个）**：30 个 `directional_route` 有实现，31 个 `route_orchestration`（各批的 orchestrator / 方向注册表 / 差分语料 / 路径认证）全部兜底。也就是说**路径能转，但没有编排和认证它们的东西**。
- **G06–G12（97 个）**：整整七个批次、零真实 handler。这是链路上最大的一段连续空白——目标架构综合、代码生成内核、组件语义、状态副作用、应用边界、UI 保真、平台能力，全部只有规范。
- **G21–G30（192 个）**：全部 C 档。这些批次的 `requiredEvidenceRoles` 强制要求 `USER_JOURNEY`、`PERFORMANCE_RUN`、`CHAOS_RUN`、`PENETRATION_TEST`、`PRODUCTION_OBSERVATION` 等真实证据，且 `validateEvidence()` 会因 `item.synthetic === true` 直接判 `FRT_SYNTHETIC_EVIDENCE_NON_AUTHORITATIVE` 阻断。**没有 runner 就永远过不了。**

## 3. 主线 A：External Runner（最高优先级）

### 现状

`run()` 处理 `EXECUTE` 时，若无阻断性 typed gap，一律：

```
state   = "QUEUED"
outcome = "PROPOSAL_READY_FOR_RUNNER"
finding = FRT_EXTERNAL_RUNNER_REQUIRED (WARNING, 非阻断)
```

全仓 grep `PROPOSAL_READY_FOR_RUNNER` / `RUN_CLAIMED`，命中的只有类型定义、run store、runtime 自身和测试。`apps/runner-agent`（Java，65 个文件）**零 FRT 感知**——grep `FRT` 无任何命中，它服务的是 elmos 自有 job 模型。

### 具体断点（按修复顺序）

1. **状态机死路**：`FrtRuntime` 公开方法只有 `catalog / routes / skill / planBatch / run / getRun / audit / claim / cancel / retry`。`claim()` 把 `QUEUED → RUNNING` 之后，**没有任何方法能让 `RUNNING` 走向成功终态**。唯一出口是重启时 `#recoverInterruptedRuns()` 把它打成 `BLOCKED`。
   → 需新增 `complete(scope, runId, expectedVersion, actor, runnerResult)`，做 CAS 版本校验 + 审计。
2. **审计事件已定义但从未发出**：`frt-run-store.ts` 的 `FrtAuditEvent` 联合类型里有 `RUN_COMPLETED`，全仓无一处 emit。
   → 与第 1 项一并补齐。
3. **无结果回传通道**：Web Console 的 `app/api/frt/runs/[runId]/[operation]/route.ts` 只放行 `claim | cancel | retry` 三个操作，请求体强制只允许 `expectedVersion` 一个键（`Object.keys(body).length !== 1` 直接 400）。runner 无法回传产物、日志、退出码、证据摘要。
   → 需要新增 `complete` 操作 + 扩展请求体契约 + 相应 schema。
4. **无租约与心跳**：`contracts/runner-schema/runner-job-lease.schema.json` 是 elmos 通用租约，FRT 侧没有接入。RUNNING 的 run 没有 lease TTL、没有心跳续约，runner 静默死亡只能靠进程重启兜底。
   → 定义 FRT 租约（lease TTL、heartbeat、超时自动回 `QUEUED` 或 `BLOCKED`）。
5. **证据链未闭合**：证据目前只能由调用方在一次新的 `action: "VERIFY"` 请求里手工塞进 `request.evidence`。`frtEngineProxy.ts` 里 Console 侧发起时硬编码 `evidence: []`。runner 产出的构建日志、测试报告、截图不会自动变成 `FrtEvidenceReference`。
   → 需要 runner → 证据存储 → 内容寻址 attestation → `VERIFY` 的自动流水。注意 `validateEvidence()` 要求每个角色的 `executor !== verifier`，runner 自签会被判 `FRT_INDEPENDENT_VERIFIER_MISSING`，设计时必须留出独立 verifier 身份。
6. **产物从不落盘**：`routeMigration` 只作为内存 artifacts 返回（`frt-runtime.ts:361,376`），全仓无任何代码把生成的目标工程写到磁盘或产物库。
   → runner 需要承接产物物化 + 上传 + digest 绑定。

### 进度（2026-08-05：Vue 3 源码成为 IR 的唯一出处）

新增 `engines/frontend-client-engine/src/`：

- `frt-typed-gap-catalog.ts` —— typed gap 目录（C-4 基础设施）。46 个 code 各带 `severity` / `summary` / `remediation`；`gap()` 不再由调用点决定 severity，未登记的 code 调用即抛错。
- `frt-route-ir.ts` —— `PortableUiIr`、`FrtRouteStack`、内容寻址与 `gap()` 的共享定义（原先私有于 `directional-route.ts`）。
- `vue3-ui-ir.ts` —— 用 `@vue/compiler-sfc` + TypeScript AST 从真实 `.vue` 字节推导 IR：`view.title` / `initialCount` / `incrementBy` / `buttonLabel` 来自模板与 `<script setup>` 的字面量与整数增量；`style.accentColor` 来自 style 块；`accessibility.*` 来自源码里真实存在的 `aria-label` / `aria-live`。**推不出来的一律 typed gap + 阻断，不做默认值、不做近似。**

`convertDirectionalRoute()` 对 Vue 3 源栈的行为：

| 输入 | 行为 | `irProvenance` |
|---|---|---|
| 无 `frt-ui-ir.json` | 从源码推导 IR，再送进与声明 IR **完全相同**的严格校验器 | `SOURCE_DERIVED` |
| 有 `frt-ui-ir.json` | 仍然推导一份，并与声明值逐字段比对，任一字段不符即阻断 | `DECLARED_CROSS_CHECKED` |
| 其余 25 条路径 | 维持声明 IR（尚无 parser），结果显式标注 | `DECLARED` |

顺带修正的一处语义造假：Vue 3 fixture 原来的 `.vue` 源码里**没有任何 aria 属性**，而它声明的 IR 却断言 `mainLabel: "Counter application"` / `buttonLabel: "Increment counter"` / `liveRegion: "polite"`。这三项此前是凭空生成的无障碍承诺。现在源码里真实带上了这些属性；若去掉，`FRT_VUE3_ACCESSIBILITY_CONTRACT_NOT_IN_SOURCE` 直接阻断（有专门的负例测试）。

验证：`engines/frontend-client-engine` `tsc` + `node --test` 由 83 增至 **93 项全绿**（新增 10 项在 `test/vue3-ui-ir.test.ts`），其中包含
往返性质测试「任一源栈 → Vue 3 目标工程，再解析回来得到同一份交互契约」，以及对 title / initialCount / incrementBy / buttonLabel / accentColor / 两个 aria label 共 7 个字段的逐一篡改检测。

仍然 **未** 解决（不要据此扩大结论）：`sourceBuild` / `targetBuild` / `browserJourney` 依旧 `NOT_RUN`，`certification` 依旧 `NOT_CERTIFIED`；IR schema 仍是「单条公开 counter 路由」这一窄切片，不是通用 UI IR。

### 验收口径

一条 `EXECUTE` run 能走完 `QUEUED → RUNNING → SUCCEEDED`，产物落盘可下载，构建日志作为 `SOURCE_BUILD` / `TARGET_BUILD` 证据（`synthetic: false`、executor≠verifier）自动进入 `VERIFY`，且该 run 的 `audit` 里出现 `RUN_COMPLETED`。

## 4. 主线 B：390 个兜底 Skill 的 handler 分配

按 `handler_kind` 归并（同一 kind 内所有 Skill 共用一个分支，所以工作量是 **18 个 handler**，不是 390 个）：

| # | handler_kind | Skill 数 | 批次 | 档位 | handler 应产出什么 |
|---|---|---|---|---|---|
| 1 | `source_generation` | 13 | G06 | A | 六类目标架构骨架综合、依赖与工具链解析、项目布局、bootstrap 冒烟结论 |
| 2 | `build_toolchain` | 15 | G07 | A | AST Emitter 产物、确定性命名与文件分配、typed hole 清单、import 解析、构建诊断归一、修复循环收敛判定 |
| 3 | `route_orchestration` | 31 | G13–G17 | A | 方向注册表、差分语料选取、路径等价校验、路径认证片段 |
| 4 | `compatibility` | 15 | G18 | A | Pack 解析与冲突消解、overlay 合成结果、pack 一致性判定 |
| 5 | `cross_platform` | 14 | G12 | A | 平台能力矩阵比对、native bridge 代码生成、能力缺口清单、平台安全校验 |
| 6 | `delivery_pipeline` | 14 | G09 | A | state/effect/lifecycle/async/持久化/离线语义映射结果与语义损失清单 |
| 7 | `design_system` | 14 | G10 | A | 路由/表单/网络/存储/i18n 边界抽取、API 与错误契约映射 |
| 8 | `mobile_client` | 14 | G11 | A | UI/layout/style/asset/RTL/a11y 映射与语义化 UI 回归基线 |
| 9 | `test_automation` | 13 | G08 | A | 组件边界/props/事件/slots/hooks 映射 + 组件测试用例生成 |
| 10 | `governance` | 12 | G01 | A | 不变量注册与校验、Monorepo 边界检查、Skill 规范校验、Registry、Artifact/Provenance、Release Gate 判定 |
| 11 | `runtime_operations` | 24 | G20 | B | Skill SDK / Registry / Marketplace / CLI / Console / 多租户 / Durable Job / RBAC 审计 / 成本治理 / 部署 —— 这些是**产品自身**，不是分析结论 |
| 12 | `advanced_verification` | 19 | G19 | B | Proof obligation 生成、Lean/SMT/model checker 适配、CEGIS 循环、反例 IR、证明证据图、语义漂移检测 |
| 13 | `product_workflow` | 85 | G21/22/23/25/26 | C | 需求追溯、验收编译、业务状态机与 Saga/补偿/对账、数据契约与血缘、可用性、回归 —— 结论需真实旅程 |
| 14 | `production_readiness` | 24 | G30 | C | 发布列车、渐进发布、生产验证、事故学习 —— 需真实生产观测 |
| 15 | `security_privacy` | 23 | G29 | C | 攻击面、SAST、Fuzzing、SBOM、渗透证据 —— 需真实扫描器与渗透 |
| 16 | `administration` | 20 | G24 | C | 管理端能力矩阵、订单/退款/库存/内容/任务管理、异常处置控制台 —— 需真实 admin 旅程 |
| 17 | `performance_capacity` | 20 | G27 | C | 并发正确性、压测、容量、降级、性能预算 —— 需真实负载 |
| 18 | `resilience_dr` | 20 | G28 | C | 混沌、故障转移、区域故障、DR 演练 —— 需真实故障注入 |

**关键取舍**：第 13–18 项共 192 个 Skill 是 C 档，在主线 A 完成前写 handler 收益极低——handler 再完备，`validateEvidence()` 仍会因证据 `NOT_RUN` 判 `FRT_EVIDENCE_NOT_RUN` 阻断。建议先做 1–10（A 档 155 个，10 个 handler），再做 11–12，最后随 runner 一起做 13–18。

## 5. 主线 C：30 条路径改为真实源码解析

### 现状

`convertDirectionalRoute()` 的第一步是 `parsePortableUiIr(files, source)`，其第一行：

```ts
const raw = files["frt-ui-ir.json"];
if (raw === undefined) throw new Error("frt-ui-ir.json is required");
```

即：**30 条路径全部要求调用方预先喂一份归一化好的 Portable UI IR**，转换器只做 IR → 目标栈的 emit。唯一例外是 `FRT-1305`（Vue 3 → React），在缺少 `frt-ui-ir.json` 时走 `convertVue3ToReact(files)`，从真实源文件出发。

`validateSourceShape()` 看起来在校验源码，但实现是 `requireTokens()` ——只检查源文件里是否**出现**若干关键字（如 ArkUI 查 `@Entry`/`@Component`/`struct`/`@State`/`build`，Flutter 查 `class`/`StatefulWidget`/`State`/`Widget`/`build`）。这是形状抽查，不是解析。

六个 emitter（`emitReact` / `emitVue3` / `emitVue2` / `emitMiniProgram` / `emitArkUi` / `emitFlutter`）各约 20–60 行，产出的是骨架页面。

### 工作分解

| 项 | 内容 | 依赖 |
|---|---|---|
| C-1 | 六个真实 source parser：Vue 2 SFC、**Vue 3 SFC/`<script setup>`（已完成，`vue3-ui-ir.ts`）**、React JSX/TSX、WXML+WXSS+JS、ArkTS `.ets`、Dart Widget → Portable UI IR | 可复用 G03/G04 的 `analyzer.ts`，但需大幅扩展 |
| C-2 | 把 `parsePortableUiIr` 改为「有 `frt-ui-ir.json` 则用，否则调 C-1 的 parser」，即把 `FRT-1305` 的特例提升为通则。**Vue 3 已完成，且比原口径更严：声明的 IR 也必须与源码逐字段一致**（见下方「进度」） | C-1 |
| C-3 | 六个 emitter 从骨架升级到可构建工程（路由、状态、样式、资源、i18n 完整落地） | C-1 |
| C-4 | 每条路径的 typed gap 目录化：**已完成基础设施**（`frt-typed-gap-catalog.ts`，46 个 code 全部登记；severity 由目录集中定义，未登记的 code 直接抛错；测试断言「路由层源码里出现的 `FRT_*` 字面量集合 == 目录集合」）。仍待随 C-1/C-3 增量补录新 code | — |
| C-5 | 接入真实构建：30 条路径的 `sourceBuild` / `targetBuild` 目前 100% `NOT_RUN` | 主线 A |
| C-6 | 接入浏览器/设备证据：`browserOrDeviceEvidence` 目前 100% `NOT_RUN` | 主线 A |

### 验收口径

任取一条路径（建议先 Vue 2 → Vue 3，同族最简），只喂真实源码目录、不喂 `frt-ui-ir.json`，能产出可 `npm run build` 通过的目标工程，且未支持语义全部以 typed gap 显式列出。

## 6. 建议执行顺序

| 阶段 | 内容 | 解锁 |
|---|---|---|
| **P0** | 主线 A 第 1–3 项（`complete()` + `RUN_COMPLETED` + Console `complete` 操作） | 状态机闭环，`EXECUTE` 不再空转 |
| **P1** | 主线 A 第 4–6 项（租约心跳、证据自动化、产物落盘） | C 档 192 个 Skill 的证据通道 |
| **P2** | 主线 C 的 C-1/C-2（六个 parser + 入口改造）——**Vue 3 已落地，5/30 条路径脱离预置 IR；剩余 React / 小程序 / ArkTS / Dart / Vue 2 五个 parser** | 30 条路径脱离「预置 IR」假设 |
| **P3** | 主线 B 第 1–10 项（A 档 10 个 handler，覆盖 155 个 Skill） | G01、G06–G12、G13–G17 编排、G18 |
| **P4** | 主线 C 的 C-3/C-4 + 主线 A 第 5–6 项联调 | 首张路径证书具备签发条件 |
| **P5** | 主线 B 第 11–12 项（B 档 43 个） | G19、G20 |
| **P6** | 主线 B 第 13–18 项（C 档 192 个），随真实环境逐批推进 | G21–G30 |

## 7. 怎么判断某一项「真的做完了」

不要看目录是否存在、不要看 `surface-manifest.json` 是否生成——这两项现在 100% 齐备但 0 功能。用这三条：

1. `installed-manifest.json` 里该 Skill 的 `certification` 从 `NOT_CERTIFIED` 变为已签发，且签发方是独立 authority（`certificateFragment.externalAuthorityRequired` 为 `true`，runtime 自身永远不会签）。
2. 该 Skill 的一次 `VERIFY` run 返回 `outcome: "READY_FOR_BATCH_GATE"`，且 `evidence` 里每个 `requiredEvidenceRoles` 角色都是 `state: "PASSED"`、`synthetic: false`、`executor !== verifier`。
3. 该 Skill 对应的 surface 目录里出现了实现文件，而不只是 `surface-manifest.json`。

## 附：本清单的核验

- 各批次 Skill 数之和 = 472 ✓（与 `manifest.skill_count` 一致）
- 真实 handler 82 + 兜底 390 = 472 ✓
- 兜底档位 A 155 + B 43 + C 192 = 390 ✓
- `directional_route` 计数 30 ✓（与 `directed_route_count: 30` 及 routes 数组长度一致）
- 抽样回溯 `frt-runtime.ts` `analysisArtifacts()` 分支：`FRT-0301`(semantic_ir)→真实、`FRT-0504`(migration_planning)→真实、`FRT-1301`(directional_route)→真实、`FRT-1300`(route_orchestration)→兜底、`FRT-2915`(security_privacy)→兜底 ✓
