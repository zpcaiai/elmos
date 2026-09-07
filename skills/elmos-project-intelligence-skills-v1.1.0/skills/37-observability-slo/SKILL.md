---
name: elmos-observability-slo
description: 为接入、解析、图谱、问答、图表、文档、PPT、缓存和长任务建立指标、日志、Trace、SLO、告警和运营看板。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: operations
  title_zh: 可观测性、SLO 与运营指标
  batch: BATCH-10-scale-and-observability
  owner: elmos-project-intelligence
---

# 可观测性、SLO 与运营指标

## 目标

让质量、性能、成本、队列、失败、证据覆盖和用户体验可测量。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- service catalog
- workflow stages
- business KPIs
- error taxonomy

## 必须输出

- SLIs/SLOs
- telemetry schema
- dashboards
- alerts
- runbooks

## 执行流程

1. 定义服务和用户旅程级 SLI。
2. 统一 trace_id、job_id、project_id、analysis_run_id、artifact_id。
3. 记录队列、阶段时长、重试、缓存、Token、模型、渲染和图查询指标。
4. 记录质量指标：解析率、图完整度、引用正确率、stale 率。
5. 建立 SLO、错误预算、告警和 Runbook。
6. 实现敏感字段过滤与日志采样。

## 实施要求

- 首要 SLO 覆盖代码打开、搜索问答、分析任务、artifact 生成和恢复。
- 机器 wall-clock ETA 的实际/预测均记录。
- 业务指标与技术指标分层。
- 日志使用结构化错误码。
- 审计日志与运营日志分离。

## 安全与可信度约束

- 不得记录源代码全文、密钥或用户问题中的敏感内容。
- 不得用平均值替代尾延迟。
- 无错误预算策略的 SLO 不算完成。

## 依赖技能

- `elmos-reference-architecture`

## 预期交付物

- `observability-spec.md`
- `slo-catalog.yaml`
- `runbooks/`

## 完成定义

- [ ] 关键请求可端到端 Trace。
- [ ] 告警通过演练。
- [ ] 仪表盘能定位慢阶段和成本来源。
- [ ] 日志脱敏测试通过。
- [ ] SLO 报告可按租户和版本比较。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
