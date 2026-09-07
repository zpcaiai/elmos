# Findings — 2026-08-19 · elmos-polyglot-skills v1.0.0 检测（v2，代码级）

> 追加文件，不写入 `HANDOFF.md`（沿用 `FINDINGS-2026-08-18-claude.md` 的约定）。
> 本文件不包含任何认证声明。本次会话**未对仓库做任何写入**，除本文件本身。
> 写作者：Claude（Cowork 云端会话）　方式：只读文件系统核对，未执行 git 操作。

## ⚠️ v1 更正声明

本文件当日早些时候的 v1 版本对 64 个 Skill 逐条给出「**已实现**」。
**那个判定的口径是错的，现予撤回。**

v1 实际核对的是「仓库里存在同能力的 Skill 目录 / 引擎目录 / 契约目录」——
这是**规格层与目录层**的存在性核对。它被写成了「已实现」，读起来像代码级结论，
而代码级结论并不成立。v2 用可执行代码的存在性、体量与实际接受的输入范围重做。

**代码级结论：没有全部实现，差距是结构性的。仓库自身文档同样这么写。**

v1 中**仍然成立**的只有最终建议（不安装该包），但理由必须换：
不是「因为已实现所以不必装」，而是**该包 171 个文件里 0 行可执行代码，
装进去不会关闭任何一个代码级缺口**。

---

## 一、三层体量：规格远大于实现

| 层 | 量 | 说明 |
|---|---:|---|
| SKILL.md | **4193 份 / 512,300 行** | 规格与门禁语言 |
| JSON 规格/夹具（agent-skills+routes+contracts+schemas） | **5147 个文件** | |
| `engines/` + `modules/` 手写代码（去生成物、vendor、venv） | **203,964 行** | 真正的实现 |

**4213 个 Skill 目录中，含任何可执行文件的只有 1 个（0.02%）；
仅含 SKILL.md 的 99 个；其余 4113 个是 SKILL.md + JSON/MD 附件。**
也就是说 agent-skills 这一整层**不是实现层**，是规格层。
v1 用「b100-\*(16) 覆盖 trusted runner」这类句子做的能力认定，全部只在这一层成立。

---

## 二、`modules/` 层：真实代码，但基本只有「决策/准入」，执行面显式外置

50 个 module 合计约 5 万行。其中安全与执行相关的几个：

| module | 代码行数 | 实际内容 |
|---|---:|---|
| `security` | **36** | 单个 `SandboxPolicy` record（镜像必须 digest 钉死、禁 privileged、禁挂 docker.sock、默认拒网、命令白名单） |
| `network-policy` | **84** | `NetworkDecisionService` 决策函数 |
| `secure-execution-plane` | **127** | `SecureExecutionAdmissionService`：26 项布尔准入检查 |
| `continuous-authorization` | **145** | 授权决策器 |
| `evidence` | **103** | `ValidationPolicy.evaluate()` 判定证据齐不齐 |
| `evidence-assurance-fabric` | **186** | |

`SecureExecutionAdmissionService` 的源码注释和返回值把边界写得很清楚：

```java
/** Readiness evaluator; the scheduler, provider and enforcement receipts
    remain distinct external components. */
...
return new AdmissionResult(blockers.isEmpty() ? Decision.READY_FOR_EXTERNAL_GATE : Decision.BLOCKED, ...,
    "REAL_RUNNER_AND_SANDBOX_EXECUTION_REMAINS_AN_EXTERNAL_GATE");
```

即：**runner 证明、mTLS 通道、egress 强制、secret broker、隔离执行本身都没有实现**，
实现的是「这些条件满足了没有」的检查器。v1 说的「b100-\*(16) 全套覆盖 trusted runner」
在代码层**不成立**。

这个设计本身是自洽且诚实的（fail-closed，缺证据即 BLOCKED），
但它是**门禁平面**，不是执行平面。

---

## 三、`engines/` 层：21 个里 6 个是骨架

| 引擎 | 手写代码行数 | 判定 |
|---|---:|---|
| `frontend-client-engine` | 143,507（其中 **95,449 行是 `.generated.ts` 目录/注册表**，手写约 1.5–2 万） | 有实现 |
| `polyglot-route-engine` | 62,748（`src/` 32,735 + native 分析器） | 有实现 |
| `project-synthesis-engine` | 22,029 | 有实现 |
| `uir-java-python` | 15,807 | 有实现 |
| `component-dialect-engine` | 10,659 | 有实现 |
| `database-data-engine` | 7,445 | 有实现 |
| `sql-dialect-engine` | 3,483 | 有实现 |
| `python-engine` | 2,883 | 有实现 |
| `dotnet-engine` | 2,463 | 有实现 |
| `infrastructure-engine` | 923 | 薄 |
| `security-compliance-engine` | 857 | 薄 |
| `test-quality-engine` | 658 | 薄 |
| `enterprise-suite-engine` / `enterprise-integration-engine` / `mainframe-engine` | 519–537 | 薄 |
| `ai-platform-engine` | **65** | **骨架**：1 个 `@SpringBootApplication` + 1 个 Controller，全部转发给共享 `EvidenceBoundDomainEngine` |
| `edge-iot-industrial-engine` | **64** | 同上骨架 |
| `enterprise-architecture-engine` | **65** | 同上骨架 |
| `operations-sre-itsm-engine` | **65** | 同上骨架 |
| `software-delivery-platform-engine` | **64** | 同上骨架 |
| `composite-engine` | **0** | **无任何代码**，只有 policy JSON 与 test-fixtures |

---

## 四、跨语言转换引擎实际接受什么输入

这是全仓最核心的能力，代码级边界从 `discovery.py` 的拒绝原因码直接可读：

```
EXACTLY_ONE_FUNCTION_REQUIRED
ASYNC_FUNCTION_OUTSIDE_CERTIFIED_SUBSET
CPP_INTEGER_FUNCTION_RETURN_REQUIRED
GO_SINGLE_RETURN_TYPE_REQUIRED
GO_ELSE_IF_OUTSIDE_CERTIFIED_SUBSET / GO_IF_INIT_OUTSIDE_CERTIFIED_SUBSET
CSHARP_UNSUPPORTED_STATEMENT / CSHARP_UNSUPPORTED_TYPE
JAVASCRIPT_MODULE_IMPORT_EXPORT_OUTSIDE_CERTIFIED_SUBSET
...
```

**引擎接受的是：一个文件一个函数、整数/浮点参数与返回、无 async、无类、无异常、
无 I/O、无跨文件调用。** `Go` 连 `else if` 和 `if` 带初始化语句都在子集外。

README「能力边界速览」原文：

> 9 种引擎语言的 72 个方向已在 **`typed-pure-function-v1` 单函数仓库夹具**上完成
> 本机源运行、目标编译/运行与行为比对……
> **对象图、跨文件调用语义、异常、async、I/O、框架、数据库、并发、
> 依赖/资源/配置/测试迁移均未闭合；这不是通用仓库转换。**

---

## 五、仓库自述的执行证据状态

| 指标 | 值 | 出处 |
|---|---|---|
| 路由总数 | 176（110 `limited` + 66 `research`） | `routes/*/route.json` |
| **已认证路由** | **0** | `routes/inventory.json` |
| 本地执行证据 | `NOT_RUN`（`ENGINE_SOURCE_MANIFEST_INVALID`） | 同上 |
| 独立验证（R10） | **MISSING，0/90** | `.ai/IMPLEMENTATION_STATUS.md` |
| 形式认证（R11） | **MISSING / NOT_CERTIFIED** | 同上 |
| 全仓 gate | **98 个全部 `NOT_CERTIFIED`** | `README.md` |
| SQL 方言转写实测覆盖 | **174/1015 = 17.1%**，缺口「结构性而非增量」 | `BUSINESS_LINE_CLOSURE_MATRIX.md` |
| 大前端组件转写实测覆盖 | **8/33 = 24.2%** | 同上 |
| ChinaDB 商业 SQL 迁移 | **`SPEC_ONLY / BLOCKED`**，13 个目标 renderer 全未实现 | 同上 |
| Spring 现代化 | 仅 **4 个精确 Maven 元组** `PASSED_LOCAL`；Gradle 精确元组 `NOT_RUN` | 同上 |
| 多语言项目生成 | 8 目标真生成/构建/启动探针 + 16 个 PostgreSQL Profile —— **本业务线代码级最实** | 同上 |

---

## 六、64 个 Skill 的代码级重新分档

| 档 | 判据 | 数量 | 代表 |
|---|---|---:|---|
| **A · 有真实执行代码**（但仅在明确声明的窄子集内） | 存在会真正解析/生成/编译/比对的代码，且有本地实测记录 | 约 **14** | 10 个语言 adapter（仅 typed-pure-function 单函数子集）、`semantic-ir-builder`(polyglot-uir 18 skills 背后是 `uir-java-python` 15.8K + `modules/uir` 1039 行)、`full-project-generator`(8 目标真生成)、`frontend-ui-migrator`(54 方向真转写，覆盖 24.2%)、`spring-legacy-modernizer`(4 个精确元组) |
| **B · 只有决策/门禁代码**，执行面显式外置 | 有 Java/Python 判定器，但真正的执行/强制被标注为 external gate | 约 **16** | `trusted-runner-policy-controller`、`sandbox-environment-builder`、`scope-authorization-controller`、`production-readiness-gate`、`unified-evidence-packager`、`security-supply-chain-validator`、`immutable-repository-snapshot`、`compile-test-repair-loop` |
| **C · 只有 SKILL.md + JSON 夹具，无实现代码** | 检索 `engines/`+`modules/` 手写源码无对应执行路径 | 约 **34** | `adapter-kotlin` / `adapter-react` / `adapter-flutter`（三者 `PENDING_ANALYZER`）、`concurrency-semantics-migrator`（全仓命中 1 个文件且是无关的 registry）、`data-equivalence-validator`（命中 1）、`property-test-generator`（命中 2）、`mobile-ui-migrator`、`observability-logging-migrator`、`deployment-runtime-migrator`、`runtime-topology-correlator`、`api-contract-migrator/miner`、`data-contract-miner`、`behavior-contract-miner`、`error-nullability-migrator`、`dependency-package-remapper`、`migration-dag-builder`、`transformation-rule-dsl-author`、`delivery-pr-handoff` 等 |

> 分档口径已声明，但**这仍是抽样级判定，不是逐条执行验证**。
> 要把任何一条从 C 提到 A，唯一的办法是跑它、留证据——正是 R10/R11 一直 `NOT_RUN` 的那件事。

---

## 七、对上传包的最终建议（与 v1 相同，理由不同）

| 动作 | 建议 | 理由 |
|---|---|---|
| 安装 `elmos-polyglot-skills-v1.0.0` | **否** | 171 个文件、10126 行 SKILL.md、**0 行可执行代码**。装它一行代码级能力都不会增加，只会让 512K 行规格再涨 1 万行，把「规格:实现」的失衡推得更远 |
| 用它替换现有 Skill | **否** | 会用扁平契约盖掉 A 档那 14 项背后真实存在的引擎入口 |
| 归档保留 | 是 | SHA-256 `baf382d1fe6dbb86ebd02a4a201b6549c364fa04bd933bcb7c9b431e3b095218`，已在 `skills/` |
| 冲突项 | 记录 | 包按 14 语言 / 196 单元建模并把 javascript 当一等条目；仓库 v3 矩阵已弃用 javascript |

---

## 八、如果目标是「代码级全部实现」，真正的工作面

按缺口大小排序，均与本包无关：

1. **跨语言转换从「单函数」抬到「单文件多函数 / 类 / 异常 / async」** —— 这是 C 档 34 项里绝大多数的共同前置，也是 README 明列的未闭合项。
2. **Kotlin / React / Flutter 三个 `PENDING_ANALYZER`** —— 三个语言 adapter 目前没有分析器，A 档进不去。
3. **执行平面**（runner 隔离、证明、egress 强制、secret broker）—— 目前只有 127 行准入检查器。
4. **R10 独立验证 0/90** —— 98 个 `NOT_CERTIFIED` gate 的共同前置。
5. **6 个骨架引擎**（`composite-engine` 0 行；另 5 个各约 65 行）。

---

*本报告全部结论基于对仓库文件系统的直接读取与源码阅读；未对仓库做任何写入（本文件除外）。*
*v1 已被本文件整体取代。*
