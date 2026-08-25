---
name: elmos-diagram-spec-engine
description: 定义架构图、流程图、思维导图、数据图、API 图、部署图和安全图的统一 Diagram Spec。用于不同渲染器、编辑器和导出格式共享语义。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: artifacts
  title_zh: 统一图表语义规范
  batch: BATCH-05-diagram-platform
  owner: elmos-project-intelligence
---

# 统一图表语义规范

## 目标

以可版本化的中立 DSL 表达节点、边、分组、证据、布局约束和交互，避免图表只剩不可维护图片。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- Project Intelligence Graph view
- 图表类型
- 过滤/折叠规则
- 主题与受众

## 必须输出

- diagram-spec.json/yaml
- Schema
- validation diagnostics
- stable element IDs

## 执行流程

1. 定义 diagram metadata、nodes、edges、groups、ports、views 和 evidence refs。
2. 为 C4、BPMN、Sequence、State、ER、DFD、Mindmap、Deployment 等定义 profile。
3. 定义折叠、聚合、分页、布局 hint 和视觉语义。
4. 定义人工锁定、注释和版本 diff。
5. 实现 JSON Schema 和语义校验器。
6. 提供从 Intelligence Graph 到 Diagram Spec 的投影器。

## 实施要求

- Diagram Spec 是权威可编辑源，SVG/PNG 只是派生物。
- 节点/边 ID 跨再生成稳定。
- 显示属性与语义属性分离。
- 每个 profile 定义必需字段和允许关系。
- Schema 版本有迁移工具。

## 安全与可信度约束

- 不得将渲染器私有字段泄露为核心语义。
- 无证据节点必须标记来源类型。
- 布局变化不得造成语义 diff。

## 依赖技能

- `elmos-project-intelligence-graph`

## 预期交付物

- `schemas/diagram-spec.schema.json`
- `diagram-profiles/`

## 完成定义

- [ ] 所有目录中的核心图表类型通过 Schema。
- [ ] 相同图谱与参数生成稳定 element ID。
- [ ] 无效边和孤立证据引用被拒绝。
- [ ] Spec 可由至少两个渲染器消费。
- [ ] 版本迁移保持语义等价。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
