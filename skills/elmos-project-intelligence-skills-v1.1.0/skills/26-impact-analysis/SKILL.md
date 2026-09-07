---
name: elmos-impact-analysis
description: 分析代码、API、Schema、事件、配置、依赖、架构规则或转换补丁的直接和间接影响。用于修改前评估、PR 检查和测试选择。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: intelligence
  title_zh: 变更影响与回归范围分析
  batch: BATCH-07-search-impact-governance-analysis
  owner: elmos-project-intelligence
---

# 变更影响与回归范围分析

## 目标

生成可解释的影响半径、风险等级、受影响 artifact 和最小回归测试建议。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- base/head revision 或 proposed patch
- Intelligence Graph
- 运行热度
- 测试映射

## 必须输出

- impact graph
- affected features/APIs/data/tests/docs
- risk score
- regression plan

## 执行流程

1. 解析变更 symbol、契约、Schema、配置和部署资源。
2. 沿调用、数据、事件、部署和功能关系传播影响。
3. 应用深度、边类型、置信度和运行热度权重。
4. 识别 breaking change、数据迁移和安全边界变化。
5. 选择相关测试、文档、图表和 PPT 页面。
6. 输出确定、可能、未知影响及理由。

## 实施要求

- 支持修改前草案和实际 Git diff。
- 风险模型可配置并解释每个因子。
- 影响传播必须防图爆炸。
- 测试选择有安全上限和 fallback 全量策略。
- 可作为 PR check 返回机器可读状态。

## 安全与可信度约束

- 不得把低置信度远端影响隐藏。
- 不得仅按文件路径选择测试。
- 安全/数据契约变化不能被低风险权重稀释。

## 依赖技能

- `elmos-project-intelligence-graph`
- `elmos-runtime-trace-fusion`

## 预期交付物

- `impact-report.json`
- `regression-plan.yaml`

## 完成定义

- [ ] 基准变更集召回率优先达到目标。
- [ ] 每个受影响项可解释路径。
- [ ] 最小测试集覆盖已知失败回归。
- [ ] 受影响 artifact 被正确标 stale/regen。
- [ ] 大图分析在预算内完成或可恢复。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
