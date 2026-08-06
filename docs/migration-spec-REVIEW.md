# 跨语言仓库转换验证系统 —— 对抗式评审

**评审范围**：Batch 1–8，Skill 1–764（编号连续，无缺口，已程序化验证）
**评审立场**：假设规范存在隐藏缺陷。以下每条结论都给出可复核的依据，不接受"看起来合理"作为通过条件。
**已实现基线**：B105–B152（764 个 skill，对应 Skill 1–764，全部实现）。
**处置状态**：4 条 P0 全部裁决并落入代码；7 条 P1（评审时 6 条，实现期补充第 7 条重试预算）全部收敛；P2/P3 见文末处置表。

---

## 0. 结论摘要

| 级别 | 数量 | 说明 |
|---|---|---|
| P0 阻断 | 4 | 规范自相矛盾或存在无法执行的判定，必须先裁决才能继续实现 |
| P1 严重 | 6 (+1) | 语义重叠导致职责不清、门槛可被绕过；实现期发现第 7 族（重试预算）同类问题，一并收敛 |
| P2 一般 | 5 | 冗余、命名冲突、可维护性问题 |
| P3 提示 | 3 | 文本缺陷与工程约定 |

规范的整体方向是可靠的：把迁移当作"受约束的语义编译 + 生产认证"而不是代码翻译，这个判断在全部 8 批中保持一致，且每一批都坚持了"默认不可信、证据驱动、fail-closed"的立场。下面的问题不动摇这个骨架，但其中 4 条会让系统在真实使用时给出无法解释的判定。

---

## P0-1　认证上限表自相矛盾：3 组语言对同时出现在互斥的两档

**位置**：Batch 4 第十三节「72条路径认证上限汇总」

**证据**（程序化枚举，非人工核对）：

```
声明条目：E5=5 组 + E5-C=23 组 + E4-default=10 组 = 38 条
实际存在的无序语言对：36 组

同时出现在「通常以E5-C为目标」和「默认最高E4」两档的语言对：
  C++ <-> TypeScript
  Python <-> Rust
  Rust <-> TypeScript
```

这两档是互斥的：前者允许在生产证据下签发 E5-C，后者规定"默认最高 E4，只有冻结动态支持子集后才允许 E5-C"。同一语言对同时属于两档时，`Skill 173 Certification Ceiling Evaluator` 和 `Skill 153 Certification Ceiling Calculator` 会读到两个不同的上限，且规范没有给出优先级规则。

**影响**：这 3 组语言对涵盖 6 条定向路径。实现时若取宽松档，会让动态行为未冻结的仓库拿到 E5-C；若取严格档，则与规范中另一处白纸黑字的表述冲突。任一选择都可以被审计质疑。

**建议**：删除「默认最高E4」这一档，改为在每条路径的 Pack 内声明 `hard_cap` 字段（这也是我实现时采用的方式）。上限是路径属性，不应该同时存在于按对分组的汇总表和按路径的正文里。

---

## P0-2　Python ↔ Swift 从未被分配任何认证上限

**位置**：同上

**证据**：36 组语言对中，35 组出现在三档之一，`Python <-> Swift` 一组都没出现。但 `Skill 195 Python → Swift Pack` 和 `Skill 245 Swift → Python Pack` 都存在且各自声明了上限（均为静态 E2/E3、运行 E4、生产 E5-C）。

**影响**：汇总表被当作权威来源时，这 2 条定向路径会落入未定义状态。`Skill 165 Unsupported Feature Release Gate` 要求"不得保留未知状态"，规范自身在这里违反了这条原则。

**建议**：与 P0-1 一并处理 —— 废弃汇总表，只保留路径内声明。

---

## P0-3　7 条并行认证阶梯，没有任何组合规则

**证据**（程序化清点）：

| 阶梯 | 定义位置 | 对象 |
|---|---|---|
| E1–E5 | Skill 54–58 | 整库迁移 |
| E5-C | Batch 4 第二节 | 定向语言路径 |
| DR0–DR5 | Skill 426 | 单个替代依赖库 |
| E2–E5（框架） | Skill 322–325 | 框架迁移 |
| E2–E5（依赖） | Skill 441–444 | 依赖迁移 |
| E2–E5（基础设施） | Skill 594–597 | 数据库/缓存/消息 |
| E2–E5（通信） | Skill 759–762 | API/RPC/网关/Mesh |

规范全文没有回答这个问题：**当框架层 = E4、依赖层 = E5、基础设施层 = E3、通信层 = E5 时，这个模块的整体等级是多少？**

四个 E2–E5 阶梯共用同一套等级名称，但门槛内容完全不同。`Skill 19 Release Gate Evaluator` 明确写着"不同指标不得简单平均"，却没有说明不同阶梯之间该如何合成。

**影响**：这是最容易被误用的地方。实践中几乎必然出现"挑最高的那个报出去"，而这正是整套规范设计出来要防止的行为。

**建议**：明确采用**短板规则**（模块等级 = 各层等级的最小值），并禁止单层等级对外发布。我在实现里已经把这条写进了 `B106-S08 Evidence Level Assessor` 的 Required Checks，但规范层面需要正式裁决。另外建议把四个 E2–E5 重命名为带域前缀的形式（`FW-E4`、`DEP-E4`、`INF-E4`、`COM-E4`），避免口头交流时混淆。

---

## P0-4　"取消传播"与"支付必须完成"直接冲突

**位置**：`Skill 706 Cancellation Propagation Verifier` vs `Skill 452 Infrastructure Context and Cancellation IR` vs `Skill 17 Fault Injection Runner`

`Skill 706` 自身已经点出了矛盾："请求取消不一定意味着业务应取消。对于已提交支付，需要继续完成或进入对账。"

但 `Skill 452` 的必验项要求"取消后事务是否回滚"，`Skill 660 gRPC Deadline and Cancellation Verifier` 要求"transaction rollback"和"resource cleanup"，`Skill 744 Cancellation Race Test` 又专门构造"取消与外部支付成功同时"的场景。

三处对同一状态给出三种期望，规范没有给出判定函数。

**影响**：`Skill 744` 这类测试无法写出确定的断言 —— 不知道该断言"回滚"还是"继续完成"。差分引擎也无法判断源目标行为是否等价。

**建议**：引入显式的 `cancellation_policy` 契约，按副作用可逆性分类：

```yaml
cancellation_policy:
  reversible_effects: abort_and_rollback
  irreversible_effects_not_yet_started: abort_before_start
  irreversible_effects_in_flight: complete_then_reconcile
  unknown_outcome: reconcile_required
```

每个 endpoint 和每个 effect 必须声明所属类别，`Skill 603 Communication Side-Effect IR` 是承载这个字段的自然位置。

---

## P1-1　三套并行的消息语义模型

| Skill | 名称 | 批次 |
|---|---|---|
| 7 | Message Semantics Verifier | 1 |
| 299 | Unified Messaging IR | 5 |
| 520 | Unified Message Delivery IR | 7 |

三者的字段清单高度重合（topic、key、partition、ack、retry、dead letter、order、idempotency、transaction）。两个都叫 "Unified"，但互不引用。`Skill 301 Transactional Messaging Verifier` 与 `Skill 530 Outbox and Inbox Verifier` 是同一件事的两次表述。

**风险**：实现时会产生三份不兼容的消息 IR schema，差分引擎需要三套规范化器，而"消息只发一次"这类关键不变量会在三处各写一遍、各自演化。

**建议**：以 `Skill 520` 为唯一权威模型，`Skill 7` 降级为它在差分层的使用者，`Skill 299` 合并进 520，`Skill 301` 合并进 `Skill 530`。

---

## P1-2　四套序列化模型

`Skill 89 Data Contract IR`（Batch 3）、`Skill 258 Serialization Semantic IR`（Batch 5）、`Skill 361 Serialization Library Mapper`（Batch 6）、`Skill 629 Unified Serialization IR`（Batch 8）。

四者都要处理：unknown field、unknown enum、null vs missing、decimal、时间精度、多态判别器。`Skill 630 Field Presence Verifier` 定义的六态模型（MISSING / EXPLICIT_NULL / DEFAULTED / EMPTY / ZERO / PRESENT）是全规范里最精确的一处，但 `Skill 76 Nullability and Absence IR Builder` 只定义了四态，两者不兼容。

**建议**：以 `Skill 630` 的六态模型为准，回填 `Skill 76`。序列化 IR 统一到 `Skill 629`，其余三个改为它的领域视图。

---

## P1-3　五套上下文传播模型

`Skill 260`（框架层）、`Skill 452`（基础设施层）、`Skill 602`（通信层）、`Skill 706`（取消传播）、`Skill 719`（分布式上下文）。

字段清单几乎相同：request ID、trace、tenant、user、locale、deadline、cancellation。其中只有 `Skill 602` 提出了正确的硬性要求——"必须定义谁创建、谁传播、谁可以修改、传播到哪些调用、后台任务是否继承、请求结束后何时清理"。

**建议**：把 `Skill 602` 的六问模型提升为全局契约，其余四个只声明各自层的传播边界。

---

## P1-4　重试语义分散在四层，缺少全局预算的强制入口

`Skill 453`（基础设施重试）、`Skill 681`（网关重试）、`Skill 694`（Mesh 重试交互）、`Skill 707`（重试预算）、`Skill 743`（重试风暴测试）。

`Skill 694` 和 `Skill 722 Distributed Call Amplification Detector` 已经正确指出了放大风险（示例给出 1 个逻辑请求最坏放大到 81 次下游尝试）。但 `Skill 707` 的重试预算没有被声明为其他三处的**前置条件**——网关和 Mesh 的重试配置可以独立通过各自的验证器，然后在组合时炸开。

**建议**：把 `Skill 707` 提升为门槛型 skill，`Skill 453/681/694` 的 Required Checks 里必须引用同一份预算文档，并且 `Skill 722` 的放大系数必须小于预算才能放行。

---

## P1-5　影子子系统重复建设四次，副作用隔离规则不一致

Batch 2（Skill 26–34）、Batch 6（Skill 425）、Batch 7（Skill 586–591）、Batch 8（Skill 750–754）。

Batch 2 的 `Skill 29 Shadow Side-Effect Firewall` 定义了完整的六种拦截模式（DENY / RECORD_ONLY / STUB_SUCCESS / STUB_FAILURE / SANDBOX_EXECUTE / ISOLATED_EXECUTE）和"应用层 + 凭据层"双重保护原则。后面三批的影子 skill 都没有引用这套模型，`Skill 590 Object Storage Dual-Write Verifier` 甚至允许真实双写（"仅在明确幂等和隔离条件下"）。

**风险**：影子副作用逃逸是整套系统里后果最严重的失败模式。四套规则并存意味着最弱的那一套决定实际安全水位。

**建议**：`Skill 29` 的防火墙是唯一权威，所有影子 skill 必须声明自己使用哪种拦截模式，`Skill 590` 的双写需要单独的书面批准门槛。

---

## P1-6　证据保管与认证撤销各重复三次

- 证据：`Skill 59` / `Skill 178` / `Skill 427` / `Skill 609`
- 撤销：`Skill 60` / `Skill 428` / `Skill 763`

标题相似度最高的一对是 `Skill 60 Certification Revocation Monitor` 与 `Skill 428 Replacement Certification Revocation Monitor`（Jaccard 0.75），状态机完全相同（`VALID` / `PARTIALLY_VALID` / `REVALIDATION_REQUIRED` / `REVOKED`）。

**建议**：一个撤销引擎，按对象类型参数化。证据保管同理。

---

## P2-1　跨 skill 复用同名输出产物（21 处）

**证据**（对已实现的 326 个 skill 程序化检测）：21 个产物名被 2 个以上 skill 声明，例如：

```
mapping_report.md          : B122-S04 … B122-S16（13 个 skill）
constraint_relaxations.json: B111-S05, S06, S07, S09, S10
attack_plan.json           : B106-S06, B115-S02
counterexample_set.json    : B106-S06, B115-S03
framework_inventory.json   : B113-S04, B120-S12
```

这一点值得特别注意：仓库里 `elmos-codex-skills-batch97-104-complete/NORMALIZATION.json` 记录的历史修复类别第一条就是 `DUPLICATE_OUTPUTS`（当时影响 32 个 skill）。现有校验器只检查**单个 skill 内部**的输出重复，跨 skill 重复可以通过校验。

**建议**：给产物名加 skill 前缀，或在 manifest 层增加跨 skill 唯一性校验。

---

## P2-2　能力向量、能力匹配、鸿沟分析三处重叠

`Skill 111 Language Capability Vector` ↔ `Skill 273 Framework Capability Vector Builder`（相似度 0.54）
`Skill 133 Framework Capability Matcher` ↔ `Skill 274 Framework Gap Analyzer`（0.38）
`Skill 132 Framework Inventory and Version Resolver` ↔ `Skill 252 Framework Inventory Builder`（0.33）

Batch 3 已经建了一遍框架清单和能力匹配，Batch 5 又更细地重建了一遍，两者没有互相引用。

**建议**：Batch 3 的三个保留为语言层，Batch 5 的三个保留为框架层，但必须显式声明继承关系。

---

## P2-3　性能差分包重复七次

`Skill 34`（影子性能）、`Skill 321`（框架性能）、`Skill 423`（替代库性能）、`Skill 574–578`（数据库/缓存/搜索/对象存储/消息五个）、`Skill 748`（通信性能）。

比较维度大量重合（P50/P95/P99、吞吐、内存、CPU、连接池）。`Skill 34` 提出的关键洞察——"目标影子系统通常不执行真实副作用，因此性能可能虚假偏好"——只在这一处出现，后面六处都没有继承这个陷阱警告。

**建议**：统一性能差分底座，各领域只贡献领域特有指标和公平性约束。

---

## P2-4　认证上限计算器重复

`Skill 153 Certification Ceiling Calculator`（Batch 3）与 `Skill 173 Certification Ceiling Evaluator`（Batch 4）职责几乎相同，后者多了"按仓库实际特性加权"。`Skill 174 Unsupported Feature Downgrade` 又单独定义了降级触发。

**建议**：合并为一个计算器 + 一份降级触发表。

---

## P2-5　与仓库已有批次的命名空间

**证据**（对 `agent-skills/` 目录清单程序化比对）：现有已安装 skill 目录 643 个，批次前缀为 `b29–b34`、`b56`、`b66–b95`、`b97–b104`。新包使用的 `b105–b125` 与已有前缀**零冲突**，且全部安装名 ≤64 字符，不触发别名截断机制。

同时提醒：仓库 `AGENTS.md` 明确写着 `.agents/skills/` 的 b29–b45 属于 "Migration Pack" 命名空间，与 `agent-skills/runtime/` 的 "Product" 命名空间"数字标签永不可互换"。新包属于后者。

---

## P3-1　Batch 8 Skill 746 的表格在传递中损坏

原文为：

```
Skill 746：Compatibility Matrix Test Generator
生成矩阵
ProducerConsumer必须验证OldOld基线OldNew后向兼容NewOld前向兼容NewNew新行为Mixed rolling deploymentMixed生产升级
```

表头和单元格被压成一行，无法确定原始列结构。从内容推断应为 Producer × Consumer 的 3×2 矩阵（Old/New/Mixed），但这是推断而非事实。实现前需要你确认原表。

---

## P3-2　"E5-C" 的定义位置偏晚

`E5-C` 在 Batch 4 第二节才被定义，但 Batch 2 的 `Skill 58 E5 Certification Pipeline` 和 Batch 3 的 `Skill 153` 都早于它，且都不知道存在这个等级。任何按 Batch 1–3 实现的认证流水线都无法产出 E5-C。

**建议**：把 E5-C 回填进 `Skill 58` 的输出枚举和 `Skill 153` 的计算结果域。

---

## P3-3　764 不是 16 的整数倍

764 = 47×16 + 12。按仓库"每批恰好 16 个"的约定，全部实现后会剩 12 个。当前已实现部分用"显式声明的开放批次"处理了这个问题（B125 声明 6 个，校验器只对声明过的批次放宽）。全部实现时同样的机制适用，但需要你确认这个偏差可以接受。

---

## 附：本次评审用到的可复核检查

以下检查均已脚本化，可随规范演进重复执行：

1. 语言对覆盖与互斥性枚举（发现 P0-1、P0-2）
2. 每条定向路径上限 vs 汇总表分组对照（发现 15 处不一致）
3. 认证阶梯清点（发现 P0-3）
4. 跨 skill 输出产物唯一性（发现 P2-1，21 处）
5. 已实现 skill 的标题/目标/关键词加权相似度（发现 P2-2、P2-3，15 组候选）
6. 新旧命名空间碰撞与 64 字符限制（P2-5，零冲突）
7. 批次编号连续性（Skill 1–764 连续，无缺口）

---

## 优先级建议

先裁决 4 条 P0，它们决定实现的语义基线：

1. 废弃 Batch 4 汇总表，上限只在路径 Pack 内声明
2. 补齐 Python ↔ Swift 的上限
3. 采用短板规则合成多阶梯，四个 E2–E5 加域前缀
4. 引入 `cancellation_policy` 四态契约

P1 的六条都是"同一件事被建模多次"，可以在实现 Skill 327–764 之前统一收敛，成本远低于事后合并。


---

## 附录：最终处置状态

评审于实现开始前完成，以下是全部 18 条问题在 764 个 skill 全部落地后的处置结果。

| 级别 | 编号 | 处置 | 落点 |
|---|---|---|---|
| P0 | P0-1 上限表自相矛盾 | 裁决 ADR-MIG-P0-01：汇总表作废 | `_ceiling_with_ruling()`，72/72 路径携带唯一权威声明 |
| P0 | P0-2 Python ↔ Swift 无上限 | 裁决 ADR-MIG-P0-02：改为分级封顶推导规则 | 同上；无表格可维护即无遗漏可能 |
| P0 | P0-3 七条阶梯无组合规则 | 裁决 ADR-MIG-P0-03：短板规则 + 四个领域前缀 | `COMPOSITION_RULE`（6 处）+ 16 个领域门槛各自携带前缀声明 |
| P0 | P0-4 取消语义三处冲突 | 裁决 ADR-MIG-P0-04：按副作用可逆性的显式策略 | `CANCELLATION_RULE`（11 处） |
| P1 | 消息语义 3 套 | 收敛 ADR-MIG-P1-01 | 权威 `unified-messaging-ir` + 17 视图 |
| P1 | 序列化 4 套 | 收敛 ADR-MIG-P1-02 | 权威 `serialization-semantic-ir` + 20 视图 |
| P1 | 上下文 5 套 | 收敛 ADR-MIG-P1-03 | 权威 `framework-context-propagation-ir` + 4 视图 |
| P1 | 影子规则 4 套 | 收敛 ADR-MIG-P1-04 | 权威 `shadow-side-effect-firewall` + 18 视图 |
| P1 | 证据保管 4 套 | 收敛 ADR-MIG-P1-05 | 权威 `certification-evidence-vault` + 3 视图 |
| P1 | 撤销 3 套 | 收敛 ADR-MIG-P1-06 | 权威 `certification-revocation-monitor` + 2 视图 |
| P1 | 重试预算（实现期补充） | 收敛 ADR-MIG-P1-07 | 权威 `distributed-retry-budget-authority`（Skill 707）+ 6 视图 |
| P2 | 764 非 16 整数倍 | 显式声明的开放批次 | B152 = 12；manifest `open_batch` + 校验器 + 安装器双重强制，未声明的短批次已负控验证会被拒 |
| P2 | 缺失语义四态 vs 六态 | 统一为六态 | `nullability-and-absence-ir-builder` + `field-presence-verifier` |
| P2 | 跨 skill 同名产物 | 产物名全局唯一 | manifest 层唯一性校验 |
| P2 | 领域阶梯可被误引为核心阶梯 | 前缀 + 显式禁止声明 | 16 个门槛 skill 各一条 |
| P2 | 性能差分五处重复 | 各领域只贡献特有指标 | 6 个 `*-performance-differential-pack` |
| P3 | Skill 746 表格损坏 | **用超集消解，不猜读法**：实现完整 3×3 = 9 格 Producer × Consumer 网格 | `compatibility-matrix-test-generator`；SPEC §8 第 9 条记录原文串与消解依据 |
| P3 | 权威晚于视图的排序问题 | `authority_present` 机制 | 视图先落地即携带闭包约束，权威落地后翻标记；当前无族使用该逃生口 |
| 工程 | 交付包脚本中的硬编码常量 | **全部改为推导**：validator 的 `skill_count` 由 `len(EXPECTED_IDS)` 推出（仍独立于被检 manifest）；安装器与 `remap_global_ids` 由 manifest 推出；单元测试的批次容量与 Skill 数由 manifest 推出 | 三个交付包全部清零，`grep -E '\b(432\|592\|764)\b' scripts/ tests/` 无残留 |
| 工程 | 592 包完整安装失效（本次修复） | 已回补推导逻辑并重新生成、重新校验、实机安装验证 | `elmos-codex-skills-batch105-141-complete` 完整安装 592/592 通过；131 包同步加固 |

### 四项负控验证

对四条机制各做了一次负控，确认它们真的会拦而不是只是写在文档里：

| 机制 | 注入 | 结果 |
|---|---|---|
| 开放批次只对声明批次放宽 | 让 B140 少一个 skill（未声明为开放） | `exit 1: package Skill count or Batch range is invalid` |
| 开放批次必须显式声明 | 把 manifest 的 `open_batch` 改为 `null` | `exit 1: the declared open Batch is missing or incorrect` |
| 收敛注册表 fail-closed | 注册一个不存在的视图 slug | `exit 1: convergence registry references unknown slugs` |
| 安装器拒绝未声明的短批次 | 让 B142 的分片 manifest 少一个 skill | `exit 1: Batch 142 is short but is not the declared open Batch` |
