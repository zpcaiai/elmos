---
name: elmos-diagram-rendering
description: 把 Diagram Spec 渲染为 Mermaid、PlantUML、Structurizr、Graphviz、BPMN XML、Markmap、SVG、PNG、PDF
  和可嵌入组件。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: artifacts
  title_zh: 多格式图表生成与渲染
  batch: BATCH-05-diagram-platform
  owner: elmos-project-intelligence
---

# 多格式图表生成与渲染

## 目标

提供一致、清晰、可缩放、可缓存且可回源的自动图表输出。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- Diagram Spec
- renderer profile
- 主题/尺寸
- export format

## 必须输出

- renderer source
- SVG/PNG/PDF
- thumbnail
- render diagnostics

## 执行流程

1. 选择适合图类型的渲染器并生成中间 DSL。
2. 使用 ELK/Dagre/Graphviz 等执行自动布局。
3. 对大图进行聚合、分层、分页和 overview+detail。
4. 嵌入 element ID、evidence link 和 accessibility metadata。
5. 沙箱化渲染进程并限制 CPU/内存/时间。
6. 缓存 spec hash + renderer version + theme 的结果。

## 实施要求

- 文本不得被截断且支持中英文。
- SVG 必须消毒，禁止脚本和外部资源。
- 渲染失败返回可定位到节点/边的诊断。
- 导出结果记录 renderer/version/font substitution。
- 大图提供交互式 Web 视图而非强行单页。

## 安全与可信度约束

- 不得执行 PlantUML/Mermaid 输入中的危险 include。
- 禁止从图表 DSL 发起任意网络请求。
- 不得把低分辨率位图作为唯一导出。

## 依赖技能

- `elmos-diagram-spec-engine`

## 预期交付物

- `services/diagram-renderer`
- `render-compatibility-matrix.md`

## 完成定义

- [ ] 核心图表快照测试通过。
- [ ] 1000 节点压力图有受控降级且不 OOM。
- [ ] SVG 中 element ID 与 Spec 一致。
- [ ] 同版本确定性渲染达到目标。
- [ ] 恶意 DSL 安全测试通过。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
