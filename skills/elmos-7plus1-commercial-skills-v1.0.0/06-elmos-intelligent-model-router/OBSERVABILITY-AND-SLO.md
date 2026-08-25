# P06 可观测、SLO 与运营

## 1. SLO

| 指标 | 目标 | 说明 |
| --- | --- | --- |
| Route planning latency | P95 < 100ms | Catalog/TaskFit 热缓存 |
| Catalog freshness | < 5 min for health; <24h for metadata | 可配置 |
| Fallback success | >95% for transient provider failures | 存在合格备选时 |
| Cost accounting completeness | 100% | 所有模型回合与工具费用 |
| Budget enforcement | 100% | 硬预算不得超支，允许明确 safety margin |
| Route explainability | 100% | 每个选择有理由和策略版本 |

## 2. 必需指标

- 业务质量：requirement/capability closure、unknown gaps、Gate pass、repair rounds、人工介入。
- 运行：queue depth、active runs、step/tool latency、timeouts、retry、stalls、cancellation、recovery。
- 模型：route、Provider、input/output/cached/reasoning tokens、cost、latency、fallback、rate limit。
- 工具/环境：compiler/test/sandbox/LSP/MCP health、CPU/memory/disk/network、workspace size。
- 商业：tenant/project/job 成本、预估与实际 ETA、收入、毛利、quota、SLA 和支持事件。

## 3. 日志与 Trace

- 全部使用 correlation/causation/tenant/project/job/run/session/task/tool ids。
- 结构化事件优先；自由文本日志不得成为唯一状态来源。
- 每个 worktree/run 有独立可查询 logs/metrics/traces，便于 Agent 自助诊断。
- Prompt/代码默认不进日志；只保留 hash、分类、token 和必要审计摘要。

## 4. Dashboard

1. Executive：质量、交付、成本、毛利、SLA、认证。
2. Operations：队列、运行、stalls、Provider、沙箱、资源、错误预算。
3. Conversion：能力覆盖、差分 mismatch、unknown gap、repair、规则命中。
4. Security：deny/approval、Secret、供应链、跨租户、异常访问。
5. Learning：规则 maturity、复用、回归、drift、bad-rule escape。

## 5. 告警

- Critical Gate 被绕过、证据篡改、跨租户、Secret 泄漏、无沙箱执行：立即 P0。
- 大面积 Provider/Adapter/Session 持久化失败：P1，暂停新调度。
- 质量/成本/ETA 漂移超过策略：自动降级、回滚或切换 route。
- 文档/合同/知识过期：创建维护任务，不在客户关键运行中静默修复。
