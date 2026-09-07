---
name: elmos-repository-intelligence-semantic-ir
description: 完整发现源仓库的代码、配置、依赖、数据、消息、权限、部署与运行语义，并形成可查询 Repository Graph、Semantic IR 和 Capability Ledger。
license: Proprietary
compatibility: Codex, Claude Code, OpenCode, DeepSeek Harness, OpenHarness and native Elmos runtimes through versioned adapters
metadata:
  package_id: P02
  version: 1.0.0
  phase: "Phase 1（P0 核心护城河）"
  dependencies: "00, 01"
  maturity: commercial-product-blueprint
---

# Elmos 仓库智能与语义中间表示

## 使命

解决大型项目转换中“没看见，所以没转换”的根本问题，是完整度与未知缺口控制的基础。

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

**依赖：** P00, P01

- 不直接生成目标代码；向 P03 提供经过证据标注的 IR 和能力。
- LSP/LLM 结论必须带 provenance/confidence，不能替代 AST/编译器/运行证据。
- 对无法解析或动态生成的区域必须显式创建 blind spot，不得假装已理解。

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

- 所有源文件、构建入口和部署入口都有 discovered/ignored/unsupported 状态与理由。
- IR 不抹平事务、并发、异常、生命周期、权限、数据一致性和副作用差异。
- Capability ID 在同一源版本内稳定，可跨增量扫描追踪。
- 动态行为与静态推断冲突时保留两者并标记 conflict，不得静默覆盖。
- 每条语义结论可追溯到文件范围、符号、配置、Trace 或人工确认。
- 未知/低置信度区域进入 P05 的定向验证计划。

## 可按需加载的子 Skills

| Skill | 职责 |
| --- | --- |
| `skills/repository-inventory-scanner/SKILL.md` | 建立代码、配置、构建、测试、部署和资产的完整分类清单。 |
| `skills/language-framework-detector/SKILL.md` | 识别语言版本、框架、插件、运行时和配置约定。 |
| `skills/ast-symbol-indexer/SKILL.md` | 构建类型、符号、引用、继承、实现和注解索引。 |
| `skills/lsp-semantic-navigator/SKILL.md` | 补充定义、引用、实现和类型 hover，降低同名和 interface 映射误判。 |
| `skills/program-graph-builder/SKILL.md` | 融合依赖、调用、控制流、数据流、异常、锁和副作用图。 |
| `skills/platform-graph-builder/SKILL.md` | 建模 API、数据库、消息、缓存、定时任务、权限、配置和基础设施。 |
| `skills/runtime-trace-ingestor/SKILL.md` | 用真实请求与副作用补充动态分派、数据路径和配置分支。 |
| `skills/semantic-ir-builder/SKILL.md` | 将多语言/框架语义规范化为可转换、可验证且不丢关键差异的中间表示。 |
| `skills/capability-discovery-ledger/SKILL.md` | 把源仓库拆成稳定的业务/技术能力并追踪其发现、映射与验证状态。 |
| `skills/incremental-analysis-cache/SKILL.md` | 只重算受影响分区，同时保持与全量分析语义一致。 |
| `skills/provenance-confidence-engine/SKILL.md` | 为每个结论记录来源、时间、工具、版本、冲突和可信等级。 |
| `skills/repository-query-service/SKILL.md` | 向 Planner、Generator、Verifier 和 UI 提供安全、有界、可解释的语义查询。 |

## 必须产出

- P02 Package Manifest 与 immutable config revision
- 计划/Workpad/验收/风险/决策记录
- 本包领域输出、事件、指标和证据引用
- 兼容性、迁移与回滚记录
- P05 GateDecision 或明确 blocker

## 完成判定

- 源仓库可访问文件分类率 100%，忽略项均有策略理由。
- 关键 API/DB/MQ/cron/auth/transaction 能力无 unknown high-risk blind spot。
- IR Schema、图一致性和稳定 ID 回归全部通过。
- Capability Ledger 的每条高置信记录都有可追溯证据。
- 增量分析与全量分析在未变语义上结果一致。

## 失败处理

| 失败模式 | 强制处置 |
| --- | --- |
| 解析器版本不支持 | 回退到 token/tree-sitter/LSP/运行证据组合并标记低置信度。 |
| 代码生成产物缺失 | 定位生成入口，运行受控生成或把产物依赖记为 blocker。 |
| 动态调用无法静态确定 | 保留候选集合，注入运行 Trace/契约测试缩小范围。 |
| Monorepo 过大 | 按构建图分区、内容寻址缓存和分层摘要；全局图只保留必要边。 |
| 静态/动态证据冲突 | 创建 conflict record 并进入 P05 定向验证。 |

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
