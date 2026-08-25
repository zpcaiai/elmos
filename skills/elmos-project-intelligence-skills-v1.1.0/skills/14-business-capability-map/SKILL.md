---
name: elmos-business-capability-map
description: 从页面、API、服务、数据和已有需求发现业务域、能力、功能模块和子功能，并生成双向可追踪思维导图。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: architecture
  title_zh: 功能思维导图与业务能力地图
  batch: BATCH-04-architecture-flow-data
  owner: elmos-project-intelligence
---

# 功能思维导图与业务能力地图

## 目标

建立需求—功能—页面—API—代码—数据—测试的端到端追踪。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- Project Intelligence Graph
- UI routes
- API schemas
- 需求/README/测试

## 必须输出

- capability map
- 功能思维导图
- 功能目录
- 实现覆盖与缺口

## 执行流程

1. 识别 Actor、业务域、业务能力、功能模块和子功能。
2. 将页面、API、事件、代码、数据表、权限和测试挂接到功能节点。
3. 使用命名、调用链和文档证据生成候选功能。
4. 让用户确认、合并、拆分、重命名和排序。
5. 计算实现覆盖、测试覆盖、风险和转换状态。
6. 生成 Markmap、树形图、矩阵和可编辑 JSON。

## 实施要求

- 功能节点必须有稳定 ID 与版本。
- 业务能力与技术模块不能混为同一层。
- 支持多产品、多租户和 Feature Flag。
- 支持从代码反查功能、从功能跳代码。
- 未映射代码和未实现需求需单独列出。

## 安全与可信度约束

- 不得用 Controller 名直接替代业务能力名而不标记推断。
- 人工命名优先于自动命名。
- 隐藏/内部功能必须服从权限。

## 依赖技能

- `elmos-architecture-discovery`
- `elmos-evidence-provenance`

## 预期交付物

- `capability-map.json`
- `functional-mindmap.mm.json`
- `feature-traceability.csv`

## 完成定义

- [ ] 主要用户流程功能均可映射到 API/代码/数据。
- [ ] 功能图节点可双向导航。
- [ ] 重复功能候选可识别。
- [ ] 未映射比例可量化。
- [ ] 导出后可重新导入且不丢稳定 ID。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
