---
name: elmos-project-generation-transformation-engine
description: 将需求扩展为完整商业项目，或把源 Repository Graph/Semantic IR 变换为目标语言、框架、数据库、消息和前端平台。
license: Proprietary
compatibility: Codex, Claude Code, OpenCode, DeepSeek Harness, OpenHarness and native Elmos runtimes through versioned adapters
metadata:
  package_id: P03
  version: 1.0.0
  phase: "Phase 2（核心商业能力）"
  dependencies: "00, 01, 02, 05"
  maturity: commercial-product-blueprint
---

# Elmos 完整项目生成与多语言跨库转换引擎

## 使命

把 Elmos 从通用 Coding Agent 提升为可重复、可约束、可验证的软件生成与迁移引擎。

## 何时调用

- 用户或上游任务明确需要本包的能力范围。
- 本包依赖的输入或合同发生版本变化，需要重新构建、验证或迁移。
- P05、生产监控、上游 breaking change 或客户验收发现本包相关缺口。
- 不应调用本包来绕过其他包的边界；详见“禁止事项”。

## 必需输入

- 目标仓库或项目生成需求，以及不可变 source revision / request revision。
- 租户、项目、隐私、预算、时间、允许的模型/Provider/工具和审批策略。
- 上游 Package 输出与其 Schema 版本；缺少依赖时必须阻断。
- 选定 Phase、目标 maturity（prototype/internal-beta/commercial-ga）和认证等级。

## 依赖与边界

**依赖：** P00, P01, P02, P05

- 生成结果必须进入 P05 验证闭环；本包无权自行声明完成。
- 规则与模型不得绕过 P02 的 blind spot/uncertainty，也不得假造源语义。
- 目标栈不支持的语义必须形成 explicit gap/decision，不允许静默删除。

## 执行工作流

1. 读取本包 `PRODUCT-CAPABILITY-SPEC.md`、`ARCHITECTURE.md` 与 `ACCEPTANCE-GATES.md`，确认范围和硬不变量。
2. 执行 `readiness`：检查依赖包、Schema、源版本、权限、沙箱、模型、工具、预算和环境。
3. 创建或更新本包 Workpad：计划、验收、验证、风险、假设、阻塞与证据索引。
4. 按 `PHASE-PLAN.md` 和 `IMPLEMENTATION-BACKLOG.md` 选择最小可交付工作流，不跨越未通过的 Phase Gate。
5. 执行子 Skills；所有输出使用 `schemas/` 与根目录共享 Schema 校验，并写入版本化事件/台账。
6. 运行 `BENCHMARKS-AND-EVALS.md` 中与变更相关的定向测试和影响闭包回归。
7. 把结果送入 P05 Evidence Gate；失败则进入诊断/修复，禁止用文本声明替代证据。
8. 通过后生成 handoff：变更、证据、残余风险、成本、系统 ETA、回滚和兼容性。

## 硬不变量

- 每个 Requirement/Capability 都有目标映射、实现、验证或 explicit blocked 状态。
- 确定性规则命中后禁止被自由模型无理由覆盖；覆盖必须形成可审计 mutation decision。
- 事务、并发、消息投递、权限、数据精度、异常和副作用语义不得静默弱化。
- 生成的生产代码中 TODO/stub/mock/empty handler 必须显式计入未完成。
- 所有 Schema/API/Event 变更生成版本与迁移策略。
- 生产迁移默认可回滚，破坏性操作需审批和备份证据。

## 可按需加载的子 Skills

| Skill | 职责 |
| --- | --- |
| `skills/requirement-expander/SKILL.md` | 把自然语言和多模态输入转为功能、非功能、运营、安全、合规和验收需求图。 |
| `skills/project-archetype-engine/SKILL.md` | 为 SaaS、支付、电商、ERP、CRM、AI、IoT、工业、大数据等提供完整能力基线。 |
| `skills/architecture-synthesizer/SKILL.md` | 从需求、目标栈与质量属性生成生产级架构和 ADR。 |
| `skills/implementation-dag-planner/SKILL.md` | 把架构与能力拆成依赖明确、可并行、可验收的任务。 |
| `skills/transformation-rule-engine/SKILL.md` | 用确定性、版本化规则转换已知语言/框架语义。 |
| `skills/mutation-exception-engine/SKILL.md` | 管理项目 override、版本特例和受控偏离，不污染通用规则。 |
| `skills/multi-language-emitter/SKILL.md` | 从 Target IR 生成语言惯用、可编译且可追踪的代码。 |
| `skills/framework-platform-adapter/SKILL.md` | 映射 Spring/.NET/FastAPI/Gin/Axum/NestJS/Vue/React/Flutter/小程序等约定与生命周期。 |
| `skills/data-integration-transformer/SKILL.md` | 转换 Schema、ORM、SQL、事务、消息、缓存、文件、RPC、批处理与调度。 |
| `skills/frontend-miniapp-transformer/SKILL.md` | 转换组件、状态、路由、表单、网络、鉴权和平台能力。 |
| `skills/infrastructure-operations-generator/SKILL.md` | 生成可部署、可观测、可备份、可恢复的商业级周边。 |
| `skills/migration-controller/SKILL.md` | 用 Strangler、shadow、dual-run、流量提升和回滚降低跨库替换风险。 |

## 必须产出

- P03 Package Manifest 与 immutable config revision
- 计划/Workpad/验收/风险/决策记录
- 本包领域输出、事件、指标和证据引用
- 兼容性、迁移与回滚记录
- P05 GateDecision 或明确 blocker

## 完成判定

- 所有 requirements/capabilities 具有 closure state。
- 目标项目 build、基础运行、迁移和回滚脚本均被 P05 证据化验证。
- 关键语义没有 silent downgrade；所有 gap 有风险、owner 和处理决策。
- 生产代码中 Critical TODO/stub/mock 为 0。
- 依赖、配置、部署、观测、安全、备份和运行手册达到选定 Archetype 基线。

## 失败处理

| 失败模式 | 强制处置 |
| --- | --- |
| 目标框架不支持源语义 | 创建 gap，给出保持、模拟、重构、bridge 或人工保留方案。 |
| 规则冲突 | 按 specificity/version/confidence 排序；仍冲突则阻断并请求决策。 |
| 模型生成偏离 IR | source-map/structural validator 拒绝，重新约束生成或切换 emitter。 |
| 需求不完整 | Archetype baseline 补全并把假设显式标记为需确认/默认策略。 |
| 迁移过程数据不一致 | 停止提升流量、执行 reconcile/rollback 并保存差异证据。 |

## 禁止事项

- 禁止把“模型说已完成”“代码看起来合理”“大部分测试通过”作为完成证据。
- 禁止静默忽略 unsupported capability、低置信结论、失败 Hook、partial sandbox 或过期证据。
- 禁止跨租户复用代码、Prompt、Trace、规则或修复案例，除非有明确 scope 与授权。
- 禁止直接跟随上游 main/dev/preview；必须使用 Pin、Adapter 和 conformance tests。
- 禁止降低验收标准来修复失败；应修改实现、扩大证据或明确 blocker/waiver。

## 参考文件

- `README.md`
- `PRODUCT-CAPABILITY-SPEC.md`
- `ARCHITECTURE.md`
- `PHASE-PLAN.md`
- `INTERFACE-CONTRACTS.md`
- `DATA-AND-EVENT-MODEL.md`
- `SECURITY-AND-GOVERNANCE.md`
- `OBSERVABILITY-AND-SLO.md`
- `BENCHMARKS-AND-EVALS.md`
- `ACCEPTANCE-GATES.md`
- `FAILURE-MODES-AND-RECOVERY.md`
- `IMPLEMENTATION-BACKLOG.md`
