# P06 — Elmos 智能模型、Provider 与成本路由

**版本：** 1.0.0  
**实施阶段：** Phase 2（质量/成本/隐私优化）  
**依赖：** P00, P01, P05

## 一句话定位

按任务、语言、框架、历史质量、上下文、工具、隐私、ZDR、预算、延迟、吞吐和可用性选择模型/Provider，并管理 fallback、hedging、shadow、cost 和 ETA。

## 商业价值

让不同环节使用最匹配的模型与 Provider，提升质量、稳定性和性价比，同时避免被单一供应商锁定。

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

本包吸收：OpenRouter Go SDK, OpenRouter TypeScript SDK, OpenRouter Python SDK, OpenRouter Skills, OpenRouter TypeScript Agent。所有内容均为 Elmos 的独立规划和重新表达；外部实现只经 Adapter 或明确依赖接入。
