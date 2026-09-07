---
name: elmos-project-intelligence-graph
description: 融合代码、架构、功能、流程、数据、部署、安全和测试图谱。用于所有图表、文档、PPT、问答和影响分析的统一知识底座。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: analysis-core
  title_zh: 统一 Project Intelligence Graph
  batch: BATCH-02-graphs-and-evidence
  owner: elmos-project-intelligence
---

# 统一 Project Intelligence Graph

## 目标

建立跨视角统一节点、关系、版本和查询接口，消除各生成器各自理解项目造成的不一致。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- Code Graph
- 构建/部署配置
- API/DB/事件 Schema
- 测试与运行证据

## 必须输出

- Project Intelligence Graph
- Graph schema
- view projections
- graph quality report

## 执行流程

1. 定义统一节点和关系 taxonomy。
2. 将代码节点聚合为模块、组件、服务、业务能力和部署单元。
3. 连接 API、事件、数据资产、测试、配置和安全边界。
4. 保存每个聚合结论的证据集合与置信度。
5. 提供 C4、流程、数据、功能、部署等投影视图。
6. 版本化图谱并支持 revision diff。

## 实施要求

- 节点必须有 stable key、revision scope 和 provenance。
- 聚合算法可配置并允许人工 override。
- 图谱存储通过 Repository 接口可替换。
- 支持多仓库 System Workspace。
- 输出 graph completeness、orphan rate 和 confidence distribution。

## 安全与可信度约束

- 不得让 LLM 直接写入 Confirmed 节点；必须经证据验证器。
- 人工 override 不得被自动分析静默覆盖。
- 不可用的视图必须返回缺失证据，而不是空白成功。

## 依赖技能

- `elmos-symbol-code-graph`
- `elmos-evidence-provenance`

## 预期交付物

- `project-intelligence-graph.json`
- `graph-quality-report.json`

## 完成定义

- [ ] 同一事实在不同 artifact 中保持一致。
- [ ] 任意图节点可回到代码或运行证据。
- [ ] revision diff 能解释节点和边变化。
- [ ] 人工 override 有审计和回滚。
- [ ] 图质量指标可观测。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
