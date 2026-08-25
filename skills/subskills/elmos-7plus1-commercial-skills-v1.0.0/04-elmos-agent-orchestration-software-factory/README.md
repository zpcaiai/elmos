# P04 — Elmos 多 Agent 编排与自主软件工厂

**版本：** 1.0.0  
**实施阶段：** Phase 2（商业软件工厂）  
**依赖：** P00, P01, P02, P03, P05, P06

## 一句话定位

以 Symphony-style reconciler、任务 DAG、隔离 workspace、专业化 Agent、可续接子 Agent、Workpad、Review 和 Proof-of-Work 组织大型项目生成与跨库转换。

## 商业价值

将复杂长任务拆成可管理、可恢复、可并行、可验收的工程单元，降低单 Agent 上下文过载、自我审查和假完成。

## 文档导航

| 文件 | 用途 |
| --- | --- |
| `SKILL.md` | 给 Codex/Claude/OpenCode/Elmos Agent 使用的执行入口。 |
| `PRODUCT-CAPABILITY-SPEC.md` | 产品目标、边界、能力和商业交付。 |
| `ARCHITECTURE.md` | 组件、依赖、数据流和技术决策。 |
| `PHASE-PLAN.md` | Design→MVP→Scale→GA 的阶段任务与退出门。 |
| `INTERFACE-CONTRACTS.md` | 公共 API/SPI、错误语义和兼容规则。 |
| `DATA-AND-EVENT-MODEL.md` | 领域实体、状态、事件和持久化原则。 |
| `SECURITY-AND-GOVERNANCE.md` | 威胁模型、权限、隐私、租户和供应链治理。 |
| `OBSERVABILITY-AND-SLO.md` | 指标、日志、Trace、SLO、告警和成本。 |
| `BENCHMARKS-AND-EVALS.md` | 基准、场景、数据集、指标和回归方法。 |
| `ACCEPTANCE-GATES.md` | 机械化完成门与证据要求。 |
| `FAILURE-MODES-AND-RECOVERY.md` | 失败分类、重试、补偿、恢复和人工升级。 |
| `IMPLEMENTATION-BACKLOG.md` | 可执行工作流、任务 ID 和完成定义。 |
| `skills/*/SKILL.md` | 按需加载的子能力。 |

## 能力来源

本包吸收：OpenAI Symphony, DeepSeek Harness, HKUDS OpenHarness, OpenCode, OpenRouter TypeScript Agent。所有内容均为 Elmos 的独立规划和重新表达；外部实现只经 Adapter 或明确依赖接入。
