---
name: elmos-intelligent-model-router
description: 按任务、语言、框架、历史质量、上下文、工具、隐私、ZDR、预算、延迟、吞吐和可用性选择模型/Provider，并管理 fallback、hedging、shadow、cost 和 ETA。
license: Proprietary
compatibility: Codex, Claude Code, OpenCode, DeepSeek Harness, OpenHarness and native Elmos runtimes through versioned adapters
metadata:
  package_id: P06
  version: 1.0.0
  phase: "Phase 2（质量/成本/隐私优化）"
  dependencies: "00, 01, 05"
  maturity: commercial-product-blueprint
---

# Elmos 智能模型、Provider 与成本路由

## 使命

让不同环节使用最匹配的模型与 Provider，提升质量、稳定性和性价比，同时避免被单一供应商锁定。

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

**依赖：** P00, P01, P05

- 公开 benchmark 只作为先验，Elmos 自有任务历史与可用性 Gate 优先。
- 路由器不降低 P05 质量门；预算不足应阻断/降级范围而非偷偷降低验证。
- 隐私/ZDR/地区/数据政策是硬约束，不进入可被质量分数抵消的软排序。

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

- 先硬约束过滤，再质量/成本排序；无合格候选则明确失败。
- 路由决策记录候选、过滤理由、评分、策略版本、实时健康与最终选择。
- Provider fallback 不得改变数据保留/地区/参数/工具/Schema 要求。
- benchmark 结果必须绑定来源、日期、模型实体解析和当前可用性。
- 实验/stealth/preview 模型默认不可处理机密仓库，除非策略明确批准。
- 同一 run 中 prompt-cache 敏感的工具表与前缀保持稳定，动态开放工具而非反复重构。

## 可按需加载的子 Skills

| Skill | 职责 |
| --- | --- |
| `skills/model-provider-catalog/SKILL.md` | 统一模型能力、版本、价格、上下文、模态、参数与端点健康。 |
| `skills/task-classifier/SKILL.md` | 把 Elmos 工作拆成可路由的角色、语言、框架、规模、风险和能力需求。 |
| `skills/route-constraint-engine/SKILL.md` | 执行 ZDR、数据收集、地区、BYOK、预算、参数、上下文、模态和健康约束。 |
| `skills/benchmark-availability-gate/SKILL.md` | 把外部 benchmark 作为带来源的先验，并验证模型当前可路由。 |
| `skills/historical-taskfit-scorer/SKILL.md` | 用 Elmos 已验证任务结果估计模型在特定任务上的质量与成本。 |
| `skills/multi-objective-router/SKILL.md` | 在合格候选中优化质量、完整度、稳定性、成本、时延和缓存。 |
| `skills/fallback-circuitbreaker-hedging/SKILL.md` | 在 Provider 故障和尾延迟下保持可用，同时控制重复费用和副作用。 |
| `skills/long-context-completeness-auditor/SKILL.md` | 把 Repository Graph、IR、Ledger、目标仓库与测试送给适合全局审计的模型寻找遗漏。 |
| `skills/multimodal-route/SKILL.md` | 为 UI 截图、视频、DOM/state 和设计比较选择可靠模型。 |
| `skills/cost-token-eta-engine/SKILL.md` | 计算多轮模型、缓存、工具、并发和重试的真实/预测成本与系统墙钟时间。 |
| `skills/privacy-data-policy-broker/SKILL.md` | 控制哪些代码/数据能发往哪个 Provider，并执行 ZDR/BYOK/脱敏。 |
| `skills/route-observability/SKILL.md` | 监控候选、选择、fallback、成本、质量、drift 和策略效果。 |

## 必须产出

- P06 Package Manifest 与 immutable config revision
- 计划/Workpad/验收/风险/决策记录
- 本包领域输出、事件、指标和证据引用
- 兼容性、迁移与回滚记录
- P05 GateDecision 或明确 blocker

## 完成判定

- 无 eligible route 时明确失败，不调用不符合隐私/能力/预算的 Provider。
- 路由 trace 包含完整过滤与评分依据。
- 候选模型当前可用且具备请求所需工具/Schema/模态/输出能力。
- TaskFit 只吸收 P05 verified outcome，不吸收 Agent 自评。
- 成本、token、缓存、reasoning 和工具时间账本可对账。

## 失败处理

| 失败模式 | 强制处置 |
| --- | --- |
| Catalog/health stale | 降低置信度、主动探测、使用保守 Route 或阻断高风险任务。 |
| 所有 Provider 失败 | 保存 run state，指数退避或切换合格模型；禁止无限重试。 |
| benchmark 领先模型不可用 | 从主候选移除并解释，选择已验证可用替代。 |
| 成本预测偏差 | 逐阶段更新 ETA/成本区间，触发预算 Gate 和重规划。 |
| TaskFit 数据稀疏 | 使用外部先验+探索流量+宽置信区间，不伪造精确排序。 |

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
