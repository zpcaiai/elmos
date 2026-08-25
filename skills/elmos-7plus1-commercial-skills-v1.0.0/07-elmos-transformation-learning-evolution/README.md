# P07 — Elmos 转换知识沉淀、自学习与能力进化

**版本：** 1.0.0  
**实施阶段：** Phase 3（长期复利护城河）  
**依赖：** P00, P02, P03, P05, P06

## 一句话定位

把每次经过验证的生成、转换、失败、修复、规则、项目模式和证据沉淀为可复用知识，并通过严格晋升、基准回归和专项模型训练持续提高质量。

## 商业价值

形成属于 Elmos 自己的 Software Transformation Intelligence，使模型和 Harness 可替换，而转换能力随项目数量复利增长。

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

本包吸收：OpenAI Harness Engineering, OpenRouter Skills, Elmos proprietary transformation architecture。所有内容均为 Elmos 的独立规划和重新表达；外部实现只经 Adapter 或明确依赖接入。
