# 跨语言仓库转换验证系统 —— 合并规范

**版本**：consolidated-v1
**来源**：Batch 1–8，Skill 1–764（编号连续，已验证）
**状态**：本文档是合并、去重、统一 schema 后的规范。与原始批次冲突处以本文档为准，冲突点在 §8 逐条列出。
**P0 裁决**：4 条 P0 已裁决并落入代码（`docs/adr-p0-rulings.md`，实现见 `_apply_p0_rulings()`）。
**P1 收敛**：7 个能力族已收敛并落入代码（`docs/adr-p1-convergence.md`，注册表 `gen/convergence.py`，实现见 `_apply_p1_convergence()`）。
**实现状态**：**已完成**。Skill 1–764 全部实现为 `elmos-codex-skills-batch105-152-complete`（764 个 skill，B105–B152；B105–B151 各 16 个，B152 为声明的开放批次 12 个）。校验器与 13 项单元测试全绿。

---

## 1. 系统定位

这不是代码翻译器。每次迁移是一次**受约束的语义编译加生产认证过程**：

```
源程序
+ 源运行轨迹
+ 业务契约
→ 可执行语义规范
→ 目标实现
→ 经验证的行为等价（在声明边界内）
```

不可推翻的前提：

```
转换结果默认不可信
源系统是唯一执行规范
所有关键行为必须可观察
源目标在同一条件下双运行
所有差异必须有终态分类
测试必须能杀死真实错误
大模型不能裁决自身正确性
只有证据达到门槛才能发布
```

**禁止的结论措辞**：不得声称"对任意输入和任意未来环境已经绝对证明完全一致"。允许的最强措辞见 §5.4。

---

## 2. 分层架构

规范共 12 层。每层有独立的 IR、验证器、变异库和门槛，但共用同一套证据、差异分类和认证底座。

```
L0  治理层        控制塔、决策日志、风险账本、事故管理、隐私与成本守卫
L1  基线层        源系统冻结、可执行规范采集、行为边界定义、确定性环境注入
L2  语义 IR 层    结构/类型/值语义/缺失/多态/控制流/求值顺序/错误/生命周期/
                  副作用/状态/并发/顺序/事务/框架/元编程/数据契约/平台 ABI
L3  语言前端后端  9 个源语言前端 + 9 个目标语言后端 + 目标 IR 反向重建
L4  定向路径层    72 条定向 Profile，各带 Rule/Mutation/Test Pack 与认证上限
L5  框架层        请求管线、依赖注入、配置、绑定验证、序列化、错误管线、上下文传播
L6  依赖层        依赖知识图谱、实际使用面、标准库能力本体、替代库认证、供应链安全、许可证
L7  基础设施层    数据库、缓存、搜索、对象存储、消息中间件的驱动与协议语义
L8  通信层        REST/RPC/GraphQL/流式、Schema 演进、网关、Service Mesh、分布式调用
L9  验证层        差分执行、属性测试、模糊测试、变异测试、并发探索、故障注入
L10 影子与切流层  影子部署、流量复制、副作用防火墙、渐进切流、单写所有权、自动回滚
L11 认证层        证据保管、等级评定、上限计算、撤销监控、旧系统退役
```

**层间规则**：

- 上层可以特化下层的 IR，但不得重新定义它。
- 每层的差异都汇入同一个差异分类器（§4.3），不存在层内私有的"可忽略差异"。
- 任一层的关键失败阻断全局认证，不因其他层通过而被补偿。

---

## 3. 统一 Schema

以下 schema 是规范的机器可读核心。原始批次中重复定义的等价结构均已合并到此处。

### 3.1 Skill 契约

```yaml
skill_contract:
  schema_version: elmos.executable-skill-contract.v1
  id: string                      # B<batch>-S<nn>
  name: string                    # 安装名，[a-z0-9-]+，<=64 字符
  version: semver
  layer: L0..L11
  inputs: [identifier]            # 非空
  outputs: [artifact_name]        # 非空，全局唯一（见 §8 裁决 6）
  permissions:
    default: deny
    external_effects: authorization-required
    secrets: broker-reference-only
  steps: [{id, title, instruction, effect}]        # >= 10
  rollback: [{id, instruction, effect}]            # >= 1
  tests:
    unit: [instruction]           # >= 1
    integration: [instruction]    # >= 1
    negative: [instruction]       # >= 1
  evidence: [{type, required, source_section}]
  verification_states: [specified, implemented, statically_validated,
                        integration_tested, runtime_verified,
                        independently_verified, certified]
  source_hash: sha256
  signature: signature | null
```

### 3.2 源基线

```yaml
source_baseline:
  repository: string
  commit: sha
  runtime: string
  framework: string
  database: string
  image_digest: sha256
  config_digest: sha256
  dependency_digest: sha256
  created_at: rfc3339
  frozen: true                    # 冻结后禁止修改，修复必须建立新基线
```

### 3.3 行为等价 Profile

```yaml
equivalence_profile:
  rules:
    - path: string                # 字段路径或通道
      comparison: exact | tolerance | normalized | unordered_collection | relational
      tolerance: {absolute?, relative?}          # 仅 tolerance
      normalizer: string                          # 仅 normalized
      identity_key: string                        # 仅 unordered_collection
      constraints: [string]                       # 仅 relational
  forbidden:                      # 全局禁止，任何路径不得覆盖
    - float_tolerance_on_monetary_field
    - global_identifier_suppression
    - ordered_events_as_unordered_set
    - suppression_of_effect_count
    - suppression_of_row_count
    - suppression_of_error_type
```

### 3.4 缺失语义（六态，权威定义来自 Skill 630）

```yaml
absence_semantics:
  states: [MISSING, EXPLICIT_NULL, DEFAULTED, EMPTY, ZERO, PRESENT]
  rule: 六态互不等价；任何两态合并都必须有决策记录和回归测试
```

> 本定义取代 Skill 76 的四态模型。

### 3.5 副作用与意图

```yaml
effect:
  id: string
  category: database_write | cache_write | message_publish | message_ack |
            external_call | file_write | payment | notification | device_command |
            object_write | search_index | permission_change
  reversibility: reversible | irreversible
  transaction_phase: before_begin | in_transaction | before_commit |
                     after_commit | after_response
  idempotency_key: string | null
  retry_policy: {max_attempts, backoff, jitter}
  ordering_constraints: [{before, after, relation: strict|eventual|commutative}]
  compensation: string | null     # reversible 必填
  occurs_after: [effect_id]
  occurs_before: [effect_id]
```

影子模式下，未真实执行的副作用以相同结构记录为 `effect_intent`，并与源系统的真实副作用逐字段比较。**不得因为未真实执行而跳过验证。**

### 3.6 取消策略（新增，裁决 P0-4）

```yaml
cancellation_policy:
  reversible_effects: abort_and_rollback
  irreversible_effects_not_yet_started: abort_before_start
  irreversible_effects_in_flight: complete_then_reconcile
  unknown_outcome: reconcile_required
```

每个 endpoint 和每个 effect 必须声明所属类别。取消测试的断言由此表决定，不再由各层自行解释。

### 3.7 上下文传播（六问模型，权威定义来自 Skill 602）

```yaml
context_contract:
  fields: [request_id, correlation_id, trace_context, baggage, user, service_identity,
           tenant, locale, timezone, deadline, cancellation, idempotency_key,
           feature_flag, routing_hint, security_claim]
  per_field:
    created_by: string
    propagated_by: [boundary]
    mutable_by: [component]
    propagates_to: [call_type]
    inherited_by_background_task: true | false
    cleared_at: phase
```

### 3.8 重试预算（全局，裁决 P1-4）

```yaml
retry_budget:
  logical_request_id: string
  total_attempt_ceiling: integer          # 全链路上限，非单层
  per_layer:
    client: {max_attempts, per_try_timeout_ms}
    gateway: {max_attempts, per_try_timeout_ms}
    mesh: {max_attempts, per_try_timeout_ms}
    application: {max_attempts, per_try_timeout_ms}
    driver: {max_attempts, per_try_timeout_ms}
  amplification_ceiling: integer          # 必须 >= 实测最大放大系数
  non_idempotent_retry: forbidden
```

网关、Mesh、驱动层的重试配置**必须引用同一份预算文档**。放大检测器实测值超过 `amplification_ceiling` 即阻断。

### 3.9 差异记录

```yaml
difference:
  id: string
  scenario_id: string
  layer: L0..L11
  channel: response | exception | db_state | cache | message | external_call |
           ordering | resource | performance | context | schema
  source_behavior: any
  target_behavior: any
  initial_state_ref: string
  environment_ref: string
  severity: critical | high | medium | low
  classification: TARGET_REGRESSION | SOURCE_BUG | INTENTIONAL_CHANGE |
                  ORACLE_CONFLICT | ENVIRONMENT_DIFFERENCE | NONDETERMINISM |
                  UNSUPPORTED_FEATURE | UNRESOLVED
  minimal_repro: string
  owner: identity
  approver: identity | null
  regression_test: string | null
```

**放行条件**：`UNRESOLVED = 0`。这是所有发布阶段的硬性条件，不接受任何层级的例外。

### 3.10 影子副作用防火墙（权威定义来自 Skill 29）

```yaml
side_effect_firewall:
  modes: [DENY, RECORD_ONLY, STUB_SUCCESS, STUB_FAILURE, SANDBOX_EXECUTE, ISOLATED_EXECUTE]
  dual_protection_required: true      # 应用层替换 + 网络或凭据层限制，缺一不可
  rules:
    - operation: string
      mode: <modes>
      rewrite_topic: string | null
      rewrite_bucket: string | null
  block_if: any_irreversible_effect_class_lacks_deterministic_interception
```

**所有层的影子机制**（L10 主影子、依赖替代影子、基础设施影子、通信影子）必须声明使用哪种模式，不得自建规则。真实双写需要单独的书面批准。

### 3.11 认证记录

```yaml
certification:
  subject: {repository, module, source_commit, target_commit}
  scope: {language_path, framework, environment, routes, input_space, time_window}
  layer_levels:
    core: E1..E5 | E5-C
    directional_path: E1..E5 | E5-C
    framework: FW-E2..FW-E5
    dependency: DEP-E2..DEP-E5
    infrastructure: INF-E2..INF-E5
    communication: COM-E2..COM-E5
    replacements: [{package, level: DR0..DR5}]
  composed_level: <min of all layer levels>      # 短板规则，见 §5.3
  ceiling: E1..E5 | E5-C
  evidence_bundle_uri: string
  pack_versions: {rule, mutation, test}
  toolchain: {compiler, runtime, framework, platform}
  status: VALID | PARTIALLY_VALID | REVALIDATION_REQUIRED | REVOKED
  issued_at: rfc3339
  expires_on_change_of: [causal_input]
```

### 3.12 定向路径 Pack

```yaml
directional_pack:
  id: <source>-to-<target>
  version: semver
  source_language_range: string
  target_language_range: string
  supported_frameworks: [string]
  rules: {type, error, concurrency, lifetime, dependency, framework}
  lints: [string]
  mutations: [operator]
  tests: {contract, property, fuzz, concurrency, shadow}
  unsupported_features: [{type, severity, resolution}]
  failure_history: [regression_id]
  certification_ceiling:
    static_only: E1..E5
    with_runtime_trace: E1..E5
    with_production_evidence: E1..E5 | E5-C
    hard_cap_e3_conditions: [unexplained_undefined_behaviour, incomplete_dynamic_trace_coverage]
    hard_cap_e4_conditions: [enumerated_dynamic_behaviour_not_frozen]
    # 任何批准都无法突破，只有新证据可以解除
```

> 上限**只在此处声明**。Batch 4 第十三节的按语言对汇总表已废弃（§8 裁决 1、2）。

---

## 4. 核心机制

### 4.1 差分执行

同一输入、同一初始状态、同一注入环境下双运行，比较全部声明通道：

```
Response │ Exception │ DB delta │ Cache delta │ Messages │ External calls
Ordering │ Resource  │ Trace    │ Performance │ Context  │ Schema decode
```

差分级别：请求级 → 实体级 → 会话级 → 时间窗口级 → 统计级。

**目标系统自身测试通过不构成放行依据。**

### 4.2 确定性注入

源目标必须共用：同一时间、同一时区、同一随机种子、同一标识符序列、同一外部服务返回、同一调度脚本、同一数据库初始状态、同一消息初始状态。

任一系统仍直接调用系统时钟、随机库或未拦截的网络，即视为不满足前提。

### 4.3 差异分类

每个差异必须获得终态分类（§3.9）。仅以下五种情形可放行：

1. 目标缺陷已修复
2. 源缺陷已确认且业务批准修复
3. 有意变更已正式批准
4. 环境差异有充分证据
5. 非确定性已被控制或定义为可接受

### 4.4 变异有效性

```yaml
mutation_gate:
  critical_semantic_mutations: 100%
  critical_framework_mutations: 100%
  critical_concurrency_mutations: 100%
  critical_security_mutations: 100%
  critical_schema_mutations: 100%
  critical_idempotency_mutations: 100%
  overall_critical_module_score: ">= 90%"
  critical_mutants_survived: 0
```

### 4.5 角色分权

| 角色 | 职责 | 禁止 |
|---|---|---|
| 构建者 | 解析、生成、迁移、诊断、修复 | 宣布自身正确；删除或弱化测试；未记录地改变行为 |
| 攻击者 | 独立假设存在隐藏不等价，寻找最小反例 | 接受构建者结论；与构建者共用身份或运行上下文 |
| 客观工具 | 执行、测量、比较、证明、阻断 | —— |

模型可以分析、生成、诊断、修复、寻找反例；**不得作为唯一权威 oracle 或认证者**。

---

## 5. 认证模型（合并 7 条阶梯）

### 5.1 核心阶梯

| 等级 | 含义 | 必须通过 |
|---|---|---|
| E1 | 可构建、可启动 | 源目标可重复构建、部署、配置加载、migration、健康检查、优雅关闭 |
| E2 | 已有契约通过 | 原测试 100%、契约测试 100%、API/DB/消息/配置/错误码 schema 兼容、跳过项已批准 |
| E3 | 行为差分通过 | 差分、属性、边界、模糊、变异、历史流量回放、关键不变量、未解释差异为零 |
| E4 | 生产工程通过 | 并发、调度探索、故障注入、性能基线、压力、稳定性、目标平台真机、安全、回滚演练、数据兼容、副作用隔离 |
| E5 | 生产高置信一致 | 大规模回放、在线影子、关键场景全覆盖、canary 全阶段、对账、自动回滚、稳定观察期 |

### 5.2 E5-C

`E5-C` 表示：代码位于明确支持子集内、动态行为已冻结、不支持特性为零、且完成生产影子认证时才可达到的 E5。存在任何无法枚举的动态行为时，上限维持 E4。

E5-C 是 `Skill 58` 输出枚举与上限计算结果域的合法取值（§8 裁决 8）。

### 5.3 多阶梯合成（裁决 P0-3）

四个领域阶梯重命名为带域前缀：`FW-E*`（框架）、`DEP-E*`（依赖）、`INF-E*`（基础设施）、`COM-E*`（通信）。替代库使用 `DR0–DR5`。

**合成规则 —— 短板**：

```
composed_level = min(core, directional_path, FW, DEP, INF, COM, min(DR of critical replacements))
```

- 单层等级**不得单独对外发布**。
- 关键替代库的 DR 等级参与合成；非关键替代库不参与，但其未关闭风险仍阻断。
- 任一层的关键失败（金额、权限、租户、事务、幂等、不可逆副作用、Schema 兼容）直接使合成结果为 `blocked`，不进入取最小值。

### 5.4 允许的结论措辞

```
在已声明的业务边界、支持矩阵、生产输入覆盖范围、
运行环境和可观察行为范围内，
目标系统与源系统达到 <composed_level> 级一致。
```

### 5.5 撤销

任一因果输入变化时，状态从 `VALID` 降级，不得保持有效。恢复只能通过新证据，不能通过批准。

因果输入包括：目标代码、依赖、运行时、数据库、框架、配置、基础设施、流量结构、新业务场景、严重生产故障、新发现的源系统隐藏行为、安全漏洞、Pack 版本、序列化库、网关/Mesh 策略、TLS 策略、新客户端、新生产 payload、协议版本。

---

## 6. 全局硬性不变量

以下条件任一不满足即阻断认证，不接受性能改善、进度压力或高分补偿：

**金额**：总资产守恒；精度、scale、rounding、溢出行为保持；金额不得映射到二进制浮点类型（除非源系统本身如此且业务批准）。

**权限与租户**：权限降低不得增加能力；未授权请求不得产生持久化或外部副作用；跨租户访问计数为零；目标框架默认允许不得替代源框架默认拒绝。

**事务**：提交与回滚决策一致；隔离级别不得静默降低；事务边界位置一致；未知提交结果不得盲目重试。

**幂等与副作用**：相同幂等键最多产生一次外部副作用；重复消息不得重复修改业务状态；不可逆副作用不得在影子中真实执行。

**消息**：发布与消费计数一致；ack 相对提交的时机一致；顺序约束不得静默放宽；业务回滚后不得已发布消息。

**Schema**：字段号不得重用；消费者必须有明确 unknown enum 策略；新增 required 字段不视为向后兼容变更（除非传输层与消费者有明确默认处理）。

**数据兼容**：回滚窗口内，旧系统必须能读取目标写出的全部数据。

**内存安全**（涉及 native 时）：use-after-free、double free、越界、数据竞争、无效释放、关键泄漏、未定义行为、未解析 FFI 所有权，全部为零。

**供应链**：未签名 native 二进制、未解决的关键漏洞、未批准的仓库源、恶意安装脚本、未知发布者，全部为零。

**许可证**：未知关键许可证、禁用许可证、缺失必需声明、未解决的商业限制，全部为零。

**未解释差异**：`UNRESOLVED = 0`。

---

## 7. 能力去重登记

原始 764 个 skill 中，以下能力族被重复建模。本规范指定唯一权威，其余降级为领域视图。

**七个族已裁决并落入代码**（ADR-MIG-P1-01…07，注册表见 `gen/convergence.py`）。权威优先设在**已实现**的那一个
上，更丰富的字段集合并进去 —— 避免悬空引用。视图额外携带闭包约束：选中视图时必须同时加载其权威 skill，
因此权威所在批次靠后不影响运行时可用性。第七族（重试预算）的权威 Skill 707 在实现顺序上晚于其视图，
期间由 `authority_present: False` 机制承载：视图照常携带视图子句与闭包约束，构建不要求一个尚未写出的
skill 存在；Skill 707 落地后标记翻回 True。该机制保留给未来同类情形。

注册表是 **fail-closed** 的：权威或视图 slug 若指向不存在的 skill，构建直接失败而非静默丢弃子句（已负控验证）。

| 能力族 | 权威 | 合并入权威的条目 | 保留为领域视图 |
|---|---|---|---|
| 消息语义 | `unified-messaging-ir`（B123-S11，合并 Skill 7 / 520 字段集） | 299, 520 | 17 个视图 |
| 序列化 | `serialization-semantic-ir`（B121-S02，合并 Skill 89 / 361 / 629 字段集） | 89, 361, 629 | 20 个视图 |
| 缺失语义 | `nullability-and-absence-ir-builder`（B109-S12，四态升级为六态） | 630 | 由 `field-presence-verifier` 在通信层执行 |
| 上下文传播 | `framework-context-propagation-ir`（B121-S04，合并六问模型） | 452, 602, 719 | 4 个视图 |
| 重试预算 | `distributed-retry-budget-authority`（Skill 707，B149-S03） | 453 | 6 个视图 |
| 影子防火墙 | `shadow-side-effect-firewall`（B106-S13） | 425, 586–591, 750–754 | 18 个视图 |
| 证据保管 | `certification-evidence-vault`（B108-S11） | 178, 427, 609 | 3 个视图 |
| 认证撤销 | `certification-revocation-monitor`（B108-S12） | 428, 763 | 2 个视图 |
| 上限计算 | Skill 173 | 153, 174（并入降级触发表） | —— |
| 能力向量 | Skill 111（语言） | —— | 273（框架层，须声明继承） |
| 框架清单 | Skill 252 | 132 | —— |
| 能力匹配 | Skill 274 | 133 | —— |
| 性能差分 | 统一底座（新建） | 34, 321, 423, 574–578, 748 | 各领域仅贡献特有指标 |
| 副作用建模 | Skill 82（IR） | —— | 5（捕获）, 30（意图记录） |
| 差分执行 | Skill 4 | —— | 552, 642, 419（领域特化） |

**合并原则**：权威条目定义 schema 与不变量；领域视图只声明本层的采集点、特化字段和门槛，不得重新定义状态机或放宽不变量。

---

## 8. 与原始批次的冲突裁决

| # | 冲突 | 裁决 |
|---|---|---|
| 1 | Batch 4 汇总表中 3 组语言对同时属于互斥两档 | **已裁决 ADR-MIG-P0-01**：汇总表作废，上限只在 `directional_pack.certification_ceiling` 内声明；72 条路径全部声明「本 Pack 是其上限的唯一权威」 |
| 2 | Python ↔ Swift 未分配上限 | **已裁决 ADR-MIG-P0-02**：改为分级封顶规则推导，不再维护表格；全 72 向对称，无遗漏 |
| 3 | 7 条并行认证阶梯无组合规则 | **已裁决 ADR-MIG-P0-03**：短板规则；四个领域阶梯加 `FW-`/`DEP-`/`INF-`/`COM-` 前缀；单层等级禁止单独发布 |
| 4 | 取消语义三处冲突 | **已裁决 ADR-MIG-P0-04**：`cancellation_policy` 四态契约为唯一 oracle，各层不得再自行解释 |
| 5 | 缺失语义四态 vs 六态 | 采用六态（§3.4） |
| 6 | 跨 skill 复用同名输出产物 | 产物名全局唯一；manifest 层增加跨 skill 唯一性校验 |
| 7 | 影子副作用规则四套并存 | Skill 29 的六模式加双重保护为唯一权威（§3.10） |
| 8 | E5-C 定义晚于 E5 流水线 | 回填进 Skill 58 输出枚举与上限计算结果域 |
| 9 | Batch 8 Skill 746 表格损坏 | **已用超集读法消解**：源文串为 `ProducerConsumer必须验证 / OldOld基线 / OldNew后向兼容 / NewOld前向兼容 / NewNew新行为 / Mixed rolling deployment / Mixed生产升级`。与其在若干读法中猜一种，改为实现 Producer × Consumer 在 {Old, New, Mixed} 上的**完整 3×3 = 9 格**：四个纯格承载原文命名的四项（基线/后向/前向/新行为），五个混合格承载 rolling deployment、生产升级以及两侧都未滚完的真实中间态。9 格是原文任何读法的超集，因此读法歧义不再影响正确性；并显式禁止由其他格推断任一格 |
| 10 | 764 非 16 整数倍 | 使用显式声明的开放批次；manifest 声明 `open_batch`，校验器只对声明批次放宽 |

---

## 9. 完整执行闭环

```
冻结源系统
→ 建立可执行规范与行为边界
→ 控制非确定性
→ 建立仓库语义清单与稳定符号身份
→ 构建 Semantic IR 全层
→ 采集动态运行时行为
→ 选择定向路径 Profile 与其 Pack
→ 分析语义鸿沟
→ 依赖、框架、基础设施、通信四层各自建模与映射
→ 生成目标骨架与显式适配层
→ 生成目标实现
→ 从目标代码反向重建 IR
→ 源目标 IR 双向差分，检测语义丢失与语义扩张
→ 执行契约、属性、模糊、并发、故障、变异全套测试
→ 构建者依据证据修复
→ 攻击者独立寻找最小反例
→ 客观工具裁决
→ 全部差异获得终态分类
→ 生产影子（副作用全隔离）
→ 渐进切流（单写所有权 + 自动回滚）
→ 数据与副作用对账
→ 各层门槛评估，短板合成
→ 签发认证
→ 排空旧系统依赖
→ 旧系统冻结与退役
```

**最终判据**不是"目标系统能够运行"，而是：

```
在相同输入、初始状态、客户端版本、Schema、
框架与网关策略、故障条件和并发调度下，
源系统与目标系统产生的响应、状态变化、事务结果、
错误、重试、上下文传播、时序和业务副作用高置信一致。
```

---

## 附录 A：实现映射

| 规范范围 | 实现批次 | 状态 |
|---|---|---|
| Skill 1–25 | B105（16）+ B106 前 9 | 已实现 |
| Skill 26–70 | B106–B109 | 已实现 |
| Skill 71–168 | B109–B114 | 已实现 |
| Skill 169–251 | B115–B120 | 已实现 |
| Skill 252–326 | B120–B125 | 已实现 |
| Skill 327–445 | B125（补 10）+ B126–B131 | 已实现 |
| Skill 446–592 | B132–B141 | 已实现 |
| Skill 593–764 | B142–B152（B152 = 12，声明的开放批次） | 已实现 |

**总计**：764 / 764，48 个批次，2427 个文件。规范范围与实现范围现已完全一致。

72 条定向路径已全部注册为独立 skill 并程序化验证（9×8 全覆盖，无缺无重）。
