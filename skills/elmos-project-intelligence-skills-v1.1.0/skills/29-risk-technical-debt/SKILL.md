---
name: elmos-risk-technical-debt
description: 结合复杂度、变更历史、耦合、覆盖率、漏洞、运行错误和业务关键度识别技术债与高风险区域。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: intelligence
  title_zh: 风险、热点与技术债分析
  batch: BATCH-07-search-impact-governance-analysis
  owner: elmos-project-intelligence
---

# 风险、热点与技术债分析

## 目标

生成可证据化、可排序、可行动的风险和现代化优先级，而非泛泛代码评价。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- Code/Intelligence Graph
- Git history
- test coverage
- security/performance findings

## 必须输出

- risk register
- heatmaps
- debt backlog
- modernization priorities

## 执行流程

1. 计算复杂度、重复、循环、扇入扇出、变更频率和 ownership。
2. 融合测试覆盖、故障、延迟、漏洞、过期依赖和业务关键度。
3. 生成文件/模块/服务级风险评分并解释因子。
4. 识别 God module、shotgun surgery、orphan code、unstable dependency。
5. 形成修复候选、成本区间和依赖顺序。
6. 生成热力图和趋势。

## 实施要求

- 风险评分权重可配置且记录版本。
- 缺失数据不默认按零风险。
- 区分事实指标与模型建议。
- 支持当前/目标和转换前/后对比。
- 建议必须关联预期收益和验证方式。

## 安全与可信度约束

- 不得把 LOC 大自动等同高风险。
- 不得用个人贡献排名进行惩罚性评估。
- 安全漏洞严重度不得被平均分掩盖。

## 依赖技能

- `elmos-project-intelligence-graph`
- `elmos-impact-analysis`

## 预期交付物

- `risk-register.yaml`
- `technical-debt-backlog.yaml`
- `risk-heatmap.json`

## 完成定义

- [ ] 风险排序在历史缺陷回放中有可测预测力。
- [ ] 每项技术债有证据、owner、影响和完成条件。
- [ ] 热力图可下钻。
- [ ] 数据缺失明确展示。
- [ ] 优先级变化可解释。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
