---
name: elmos-flow-discovery
description: 发现业务流程、请求链、异步事件链、定时任务、状态机、异常、重试和补偿。用于流程梳理、泳道图、时序图和运行风险分析。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: architecture
  title_zh: 业务与技术流程发现
  batch: BATCH-04-architecture-flow-data
  owner: elmos-project-intelligence
---

# 业务与技术流程发现

## 目标

从入口到结束状态构建带分支、数据、副作用和证据的可执行流程模型。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- Code/Intelligence Graph
- 入口清单
- 状态与事件
- Trace/测试

## 必须输出

- Flow IR
- 业务流程
- 技术调用链
- 异常/补偿路径
- 流程质量报告

## 执行流程

1. 枚举 HTTP、GraphQL、gRPC、UI、Consumer、Cron、CLI、Webhook、Agent Task 等入口。
2. 按控制流和调用图扩展步骤，识别条件、循环、并行和异步边。
3. 关联状态变化、数据库写入、事件、外部调用和权限检查。
4. 发现超时、重试、幂等、死信和补偿。
5. 用 Trace/测试确认高价值路径。
6. 生成 BPMN、泳道、时序、状态机和普通流程视图。

## 实施要求

- Flow IR 保留步骤类型、Actor、系统、输入输出、前置/后置条件。
- 支持 happy path、error path、compensation path。
- 图过大时按业务阶段折叠。
- 每条路径有 coverage 和 confidence。
- 流程节点可直接跳代码、API、表和 Trace。

## 安全与可信度约束

- 静态不可达不等于运行时不可达。
- 不得忽略异常分支来生成“漂亮”流程。
- 循环和递归必须有截断与摘要。

## 依赖技能

- `elmos-symbol-code-graph`
- `elmos-runtime-trace-fusion`

## 预期交付物

- `flow-ir.json`
- `flow-catalog.md`
- `flow-quality-report.json`

## 完成定义

- [ ] 基准流程的主要步骤、状态和副作用完整。
- [ ] 异常、重试和补偿可独立查看。
- [ ] Trace 能覆盖并确认已执行路径。
- [ ] 流程图与 Flow IR 往返不丢语义。
- [ ] 入口清单覆盖率可量化。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
