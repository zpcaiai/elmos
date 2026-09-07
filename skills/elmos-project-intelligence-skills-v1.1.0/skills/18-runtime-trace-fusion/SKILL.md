---
name: elmos-runtime-trace-fusion
description: 接入 OpenTelemetry Trace、结构化日志、覆盖率和性能剖析，将实际运行边与静态图谱关联。用于确认流程、发现动态调用和比较静态/运行架构。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: architecture
  title_zh: 运行时 Trace、日志与静态图谱融合
  batch: BATCH-04-architecture-flow-data
  owner: elmos-project-intelligence
---

# 运行时 Trace、日志与静态图谱融合

## 目标

在不把有限观测误当完整事实的前提下，用运行证据提高架构、流程和影响分析可信度。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- OTLP traces
- logs/metrics
- environment/time window
- Code/Intelligence Graph

## 必须输出

- runtime graph
- static-runtime diff
- trace links
- coverage and hot-path reports

## 执行流程

1. 接收或导入 OTLP Trace/Span 与环境标签。
2. 规范化 service/resource/code attributes。
3. 将 span 关联到 API、symbol、database、message 和 external system。
4. 聚合调用频率、延迟、错误和关键路径。
5. 比较静态候选边与运行观测边。
6. 发布 runtime evidence 并触发受影响 artifact 更新。

## 实施要求

- 保留采样率、时间范围、环境和数据新鲜度。
- 支持脱敏、尾部采样和租户隔离。
- Trace 与 revision 不确定时必须标记。
- 运行图按环境分层，不合并 dev/prod。
- 支持源/目标双运行差分。

## 安全与可信度约束

- 未观测到的边不得判定不存在。
- 日志解析不得执行其中内容。
- 敏感属性必须在入口清洗。

## 依赖技能

- `elmos-project-intelligence-graph`

## 预期交付物

- `runtime-graph.json`
- `static-runtime-diff.md`
- `trace-link-report.json`

## 完成定义

- [ ] 已知 Trace 可正确映射到服务/接口/数据库。
- [ ] 静态与运行差异有明确原因分类。
- [ ] 采样限制显示在每个运行结论旁。
- [ ] 跨环境查询不会混淆。
- [ ] 高容量导入有背压与保留策略。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
