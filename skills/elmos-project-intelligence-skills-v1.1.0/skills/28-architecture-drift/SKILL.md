---
name: elmos-architecture-drift
description: 比较设计架构、静态实现架构、运行时架构和目标架构，检测新增依赖、边界破坏、未声明服务和文档过期。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: intelligence
  title_zh: 设计—代码—运行架构漂移检测
  batch: BATCH-07-search-impact-governance-analysis
  owner: elmos-project-intelligence
---

# 设计—代码—运行架构漂移检测

## 目标

持续发现实际系统偏离架构意图的位置，并驱动评审、文档更新和改造任务。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- design model
- current static graph
- runtime graph
- architecture rules

## 必须输出

- drift events
- before/after diagrams
- severity
- review tasks

## 执行流程

1. 规范化设计、静态和运行模型到统一语义。
2. 比较节点、关系、属性、所有权和安全边界。
3. 分类 expected change、undocumented change、violation、observation gap。
4. 计算影响和严重度。
5. 生成图表 diff、证据和建议动作。
6. 支持确认、接受为新设计、拒绝或创建修复任务。

## 实施要求

- 设计模型可来自 Structurizr/Diagram Spec/人工基线。
- 漂移检测绑定 base/head revision 与运行窗口。
- UI 需区分代码漂移和观测覆盖不足。
- 接受漂移需形成 ADR/审批。
- 结果可接入 PR 和周期扫描。

## 安全与可信度约束

- 不得把未观测调用视为删除。
- 不得自动修改设计基线。
- 不同环境的合法拓扑差异需配置。

## 依赖技能

- `elmos-architecture-discovery`
- `elmos-runtime-trace-fusion`
- `elmos-architecture-rules`

## 预期交付物

- `drift-report.json`
- `architecture-diff.svg`

## 完成定义

- [ ] 基准漂移场景全部正确分类。
- [ ] 误报可通过规则/override 解释性降低。
- [ ] 接受变更生成可审计基线版本。
- [ ] 文档和图表 stale 状态联动。
- [ ] PR 中新增违规边能阻断。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
