# Elmos 7+1 商业产品级 Skills Packages

**版本：** 1.0.0  
**研究与规划日期：** 2026-08-21  
**定位：** Harness-native、结果导向、证据驱动的完整项目生成与多语言跨库转换软件工厂。

## 核心结论

OpenAI/DeepSeek/OpenHarness/OpenCode/OpenRouter 提供的最强增益应进入 **可替换执行层、编排层、权限/沙箱、Session、工具、模型路由和评测方法**；Elmos 自己必须拥有 **Repository Graph、Semantic IR、Capability/Requirement Ledger、Transformation Rules、Differential Runtime、Evidence Gate 和 Learning Flywheel**。

> Harness 负责让 Agent 可靠地工作；Elmos 负责判断应该做什么、是否遗漏、语义是否正确，以及何时才算完成。

## 7+1 包目录

| ID | 目录 | 能力包 | 实施阶段 | 核心价值 |
| --- | --- | --- | --- | --- |
| P00 | `00-elmos-software-factory-master/` | Elmos 软件工厂总控与商业治理 | 全程 / Phase 0–4 | 把多个强能力模块组合成可销售、可升级、可审计、可运营的软件工厂产品，而不是一组互不兼容的 Agent 工具。 |
| P01 | `01-elmos-harness-runtime-platform/` | Elmos 可插拔 Harness 运行时平台 | Phase 1（可信执行底座） | 复用成熟 Harness 的执行能力，同时让 Elmos 的核心转换算法、数据与完成裁决保持独立可控。 |
| P02 | `02-elmos-repository-intelligence-semantic-ir/` | Elmos 仓库智能与语义中间表示 | Phase 1（P0 核心护城河） | 解决大型项目转换中“没看见，所以没转换”的根本问题，是完整度与未知缺口控制的基础。 |
| P03 | `03-elmos-project-generation-transformation-engine/` | Elmos 完整项目生成与多语言跨库转换引擎 | Phase 2（核心商业能力） | 把 Elmos 从通用 Coding Agent 提升为可重复、可约束、可验证的软件生成与迁移引擎。 |
| P04 | `04-elmos-agent-orchestration-software-factory/` | Elmos 多 Agent 编排与自主软件工厂 | Phase 2（商业软件工厂） | 将复杂长任务拆成可管理、可恢复、可并行、可验收的工程单元，降低单 Agent 上下文过载、自我审查和假完成。 |
| P05 | `05-elmos-conversion-reliability-verification-harness/` | Elmos 转换可靠性、验证与证据完成门 | Phase 1（P0 最高优先级） | 直接决定 Elmos 是否能把“生成代码”变成“可证明完成的软件工程交付”，也是降低假完成率的核心。 |
| P06 | `06-elmos-intelligent-model-router/` | Elmos 智能模型、Provider 与成本路由 | Phase 2（质量/成本/隐私优化） | 让不同环节使用最匹配的模型与 Provider，提升质量、稳定性和性价比，同时避免被单一供应商锁定。 |
| P07 | `07-elmos-transformation-learning-evolution/` | Elmos 转换知识沉淀、自学习与能力进化 | Phase 3（长期复利护城河） | 形成属于 Elmos 自己的 Software Transformation Intelligence，使模型和 Harness 可替换，而转换能力随项目数量复利增长。 |

## 推荐实施顺序

1. **Phase 0：P00** — 冻结源、合同、指标、Benchmark、安全和商业治理。
2. **Phase 1：P02 → P05 → P01** — 先理解和验证，再接入可靠 Harness；三者采用并行迭代但按 Gate 依赖收敛。
3. **Phase 2：P03 → P04 → P06** — 构建项目生成/转换、软件工厂与智能路由。
4. **Phase 3：P07** — 只吸收经过验证和授权的知识，形成复利。
5. **Phase 4：全包** — 多租户、SLA、计费、安全、灾备、E1–E5 与商业 GA。

## 最重要的产品原则

- 结果优先：项目生成与跨库转换的准确度、完整度、行为等价性和可证明性高于 Harness 炫技。
- Elmos Core 不绑定任何单一 Harness、模型或模型聚合商；所有外部能力经稳定 SPI/Adapter 接入。
- Agent 的“完成”声明不具有裁决权；只有机械化 Evidence Gate 可以把任务置为 COMPLETED。
- 所有模型可见事实、工具调用、审批、安全决策和验证证据必须可审计、可回放或明确标记为瞬态。
- 未知语义缺口比已知缺口更危险；系统必须显式计算发现覆盖率并持续压低 unknown gap。
- 规则优先、约束生成、模型兜底；经过验证的确定性转换应逐步替代重复的自由推理。
- 权限、沙箱、凭据、租户数据与生产副作用均 fail closed；禁止静默降级为更宽权限或无沙箱执行。
- 每次失败必须产生可复用的诊断、修复与回归证据，但未经跨项目验证不得晋升为可信规则。
- 仓库是系统记录：架构、计划、能力、验证、决策、数据契约和运行手册都在版本控制中可被 Agent 读取。
- 商业指标必须分场景、分规模、分难度报告；不得把内部目标值伪装成已实测的统一准确率。

## 快速使用

1. 先读根目录 `AGENTS.md`、`PHASE-MAP.md`、`DETAILED-PHASE-DELIVERY-PLAN.md`、`UPSTREAM-CAPABILITY-EXTRACTION.md` 和 `SOURCE-MANIFEST.md`。
2. 从 `00-elmos-software-factory-master/SKILL.md` 进入总控。
3. 按任务只加载相关顶层包及其 `skills/*/SKILL.md`，避免把所有文档塞入上下文。
4. 使用 `ELMOS_WORKFLOW.md` 作为仓库级执行合同模板。
5. 运行：

```bash
python3 scripts/validate_packages.py
python3 scripts/score_readiness.py
```

6. 实施中所有完成决定交给 P05，不接受 Agent 自行宣告完成。

## 交付内容

- 8 个顶层 Skills Package。
- 93 个按需加载子 Skills。
- 共享 JSON Schema、示例工作流、Ledger、Route、Gate 与转换规则。
- 源版本 Pin 与能力吸收矩阵。
- Phase 0–4 规划、KPI/Benchmark、Commercial GA 清单。
- 自动完整性验证脚本和 readiness 评分脚本。
- 每个包独立 ZIP 与一个总 ZIP。

## 重要说明

这是**产品与工程蓝图**，其中质量百分比只能作为未来研发目标，不能视为当前已实测能力。实施时必须在 Elmos 自有 Benchmark 上持续测量 observed/certified 指标。
