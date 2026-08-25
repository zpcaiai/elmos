---
name: elmos-architecture-discovery
description: 从代码、配置、构建、部署和运行证据发现业务、应用、技术、数据、部署、安全和运维架构。用于当前架构、目标架构和转换前后对比。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: architecture
  title_zh: 架构自动发现与多视角讲解
  batch: BATCH-04-architecture-flow-data
  owner: elmos-project-intelligence
---

# 架构自动发现与多视角讲解

## 目标

生成可解释、可编辑、可回源的多层架构模型与讲解。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- Project Intelligence Graph
- 部署/config
- 运行证据
- 人工架构规则

## 必须输出

- C4 L1-L4 模型
- 多视角架构
- 架构讲解
- 未知与冲突清单

## 执行流程

1. 识别系统边界、外部 Actor 和外部系统。
2. 聚合服务、容器、组件、模块和层。
3. 识别同步调用、异步事件、共享数据和部署关系。
4. 生成业务、应用、技术、数据、部署、安全视图。
5. 对照人工设计和运行证据，记录冲突。
6. 按受众生成 L0-L5 架构讲解。

## 实施要求

- 优先使用 C4/Structurizr 语义模型并可投影 Mermaid/PlantUML。
- 每个自动聚合节点保存聚合规则和成员列表。
- 支持当前、目标、前后对比和 revision diff。
- 允许人工合并、拆分、重命名并锁定。
- 架构完整度和置信度可量化。

## 安全与可信度约束

- 不得仅按目录名宣称服务边界。
- 运行时未观察到不代表不存在。
- 目标架构建议必须与当前事实分层显示。

## 依赖技能

- `elmos-project-intelligence-graph`
- `elmos-runtime-trace-fusion`

## 预期交付物

- `architecture-model.dsl`
- `architecture-explanation.md`
- `unknowns.json`

## 完成定义

- [ ] 系统上下文和容器图覆盖所有确认入口与外部依赖。
- [ ] 节点可下钻到代码成员。
- [ ] 人工 override 在重新分析后保持。
- [ ] 架构讲解关键结论有证据。
- [ ] 当前/目标模型不会混写。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
