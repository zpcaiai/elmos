---
name: elmos-software-factory-master
description: 统一 7 个能力包的依赖、工作流、产品控制面、架构约束、文档系统、版本治理、发布认证和商业运营。
license: Proprietary
compatibility: Codex, Claude Code, OpenCode, DeepSeek Harness, OpenHarness and native Elmos runtimes through versioned adapters
metadata:
  package_id: P00
  version: 1.0.0
  phase: "全程 / Phase 0–4"
  dependencies: "none"
  maturity: commercial-product-blueprint
---

# Elmos 软件工厂总控与商业治理

## 使命

把多个强能力模块组合成可销售、可升级、可审计、可运营的软件工厂产品，而不是一组互不兼容的 Agent 工具。

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

**依赖：** 无前置功能包；但必须遵守根目录共享合同。

- 不实现语言语义转换算法；只定义跨包合同、控制面和发布规则。
- 不直接执行模型调用；通过 P01/P06 调用。
- 不允许总控层绕过 P05 证据门宣布项目完成。

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

- 包之间只能通过版本化合同通信，禁止跨层直接访问内部数据库或私有实现。
- 所有可部署配置必须 schema-valid，并支持 last-known-good 回退。
- 每个发布必须绑定源版本、包版本、迁移说明、回归证据和回滚路径。
- 控制面不得持有可直接下发给 Agent 的长期生产凭据；使用短期、范围化授权。
- AGENTS.md 只做地图，不复制整套手册；详细知识通过渐进披露加载。
- 商业计划中的质量指标均标记 target / observed / certified 三种状态。

## 可按需加载的子 Skills

| Skill | 职责 |
| --- | --- |
| `skills/repository-system-of-record/SKILL.md` | 把产品知识、架构、计划、证据和运行规则变成版本化、可检索、可验证的仓库资产。 |
| `skills/workflow-contract-compiler/SKILL.md` | 把可读工作流文件编译成不可变执行合同，包含状态、Hooks、策略、并发、重试和 Gate。 |
| `skills/package-dependency-governor/SKILL.md` | 维护 7+1 包的公共 API、版本范围、兼容关系与弃用计划。 |
| `skills/architecture-invariant-linter/SKILL.md` | 把分层、依赖方向、命名、事件版本和禁止能力变成机械化检查。 |
| `skills/commercial-control-plane/SKILL.md` | 提供租户、项目、作业、成本、ETA、配额、账单和 SLA 的统一控制。 |
| `skills/release-certification/SKILL.md` | 用证据而不是人工口头判断决定版本能否灰度或 GA。 |
| `skills/documentation-gardener/SKILL.md` | 持续清理重复、过时、低质量文档和 Agent 产生的结构漂移。 |
| `skills/upstream-change-monitor/SKILL.md` | 跟踪所吸收 Harness/SDK 的架构、API、安全和许可证变化并评估 Elmos 影响。 |

## 必须产出

- P00 Package Manifest 与 immutable config revision
- 计划/Workpad/验收/风险/决策记录
- 本包领域输出、事件、指标和证据引用
- 兼容性、迁移与回滚记录
- P05 GateDecision 或明确 blocker

## 完成判定

- 所有 7 个包通过 Package Contract Test。
- 跨包循环依赖为 0，禁止依赖规则违例为 0。
- 发布候选绑定完整 SBOM、迁移与回滚方案。
- 控制面租户隔离、审计、额度和账单测试全部通过。
- E1–E5 中要求的证据齐全后才可标记 commercial-ga。

## 失败处理

| 失败模式 | 强制处置 |
| --- | --- |
| 工作流热更新无效 | 保留旧配置运行，隔离候选并输出结构化错误。 |
| 包版本不兼容 | 阻止发布，生成最小冲突集与可行升级路径。 |
| 计量事件丢失 | 写前日志 + 幂等重放 + 账单对账，禁止估算替代真实记录。 |
| 上游 breaking change | Adapter quarantine、兼容测试、回滚 Pin；核心域继续运行。 |
| 文档/代码漂移 | CI 阻断公共契约变更，自动创建文档修复任务。 |

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
