# AGENTS.md — Elmos 7+1 Repository Map

本文件只做导航，不复制详细手册。先确定任务属于哪个包，再按需加载。

## 入口
- `README.md`：总览与使用方式。
- `SKILL.md`：根路由 Skill。
- `ELMOS_WORKFLOW.md`：仓库级工作流合同模板。
- `PHASE-MAP.md`：Phase 0–4 依赖、交付物和退出门。
- `DETAILED-PHASE-DELIVERY-PLAN.md`：每个 Phase 的 workstreams、vertical slice 与退出门。
- `ELMOS-REFERENCE-ARCHITECTURE.md`：端到端商业参考架构、信任边界和状态机。
- `UPSTREAM-CAPABILITY-EXTRACTION.md`：逐仓库能力精华与 Elmos 吸收决策。
- `SOURCE-MANIFEST.md`：研究来源、版本 Pin、吸收/隔离策略。
- `KPI-AND-BENCHMARK-FRAMEWORK.md`：质量、完整度、等价性、成本与 ETA。
- `COMMERCIAL-GA-CHECKLIST.md`：商业 GA 清单。

## 顶层包
- `P00` → `00-elmos-software-factory-master/SKILL.md`：Elmos 软件工厂总控与商业治理。
- `P01` → `01-elmos-harness-runtime-platform/SKILL.md`：Elmos 可插拔 Harness 运行时平台。
- `P02` → `02-elmos-repository-intelligence-semantic-ir/SKILL.md`：Elmos 仓库智能与语义中间表示。
- `P03` → `03-elmos-project-generation-transformation-engine/SKILL.md`：Elmos 完整项目生成与多语言跨库转换引擎。
- `P04` → `04-elmos-agent-orchestration-software-factory/SKILL.md`：Elmos 多 Agent 编排与自主软件工厂。
- `P05` → `05-elmos-conversion-reliability-verification-harness/SKILL.md`：Elmos 转换可靠性、验证与证据完成门。
- `P06` → `06-elmos-intelligent-model-router/SKILL.md`：Elmos 智能模型、Provider 与成本路由。
- `P07` → `07-elmos-transformation-learning-evolution/SKILL.md`：Elmos 转换知识沉淀、自学习与能力进化。

## 路由规则
- 总体架构、版本、商业治理、发布：P00。
- Agent/Session/Tool/Sandbox/Permission/API：P01。
- 仓库扫描、AST/LSP/Graph/IR/Capability：P02。
- 需求补全、项目生成、跨语言/框架/数据库/前端转换：P03。
- Task DAG、Issue/Worktree、多 Agent、Review、Proof-of-Work：P04。
- Coverage、测试、差分、E2E、自动修复、Evidence Gate：P05。
- 模型/Provider、隐私、成本、健康、fallback、ETA：P06。
- 规则/失败/修复/Benchmark/专项模型/知识治理：P07。

## 不可绕过
- P05 是唯一完成裁决者。
- 外部 Harness/SDK 必须经 P01/P06 Adapter。
- 机密数据的 Provider 选择必须经 P06 Data Policy。
- 知识沉淀必须经 P07 scope/consent 与 P05 evidence。
- 任何生产副作用必须经 P01 permission/approval/sandbox。

## 共享合同
- `schemas/event-envelope.schema.json`
- `schemas/workflow-contract.schema.json`
- `schemas/requirement-ledger.schema.json`
- `schemas/capability-ledger.schema.json`
- `schemas/evidence-bundle.schema.json`
- `schemas/model-route-decision.schema.json`
- `schemas/transformation-rule.schema.json`
- `schemas/repair-trace.schema.json`
- `schemas/benchmark-case.schema.json`
- `schemas/policy-decision.schema.json`

## 验证命令
- `python3 scripts/validate_packages.py`
- `python3 scripts/score_readiness.py`

## 维护规则
- 公共合同变更必须更新 Schema、示例、兼容说明和回归测试。
- 文档与实现不一致时，创建修复任务；不让 AGENTS.md 膨胀成手册。
- 上游版本变化先更新 SOURCE-MANIFEST，再运行 Adapter/Benchmark 回归。
