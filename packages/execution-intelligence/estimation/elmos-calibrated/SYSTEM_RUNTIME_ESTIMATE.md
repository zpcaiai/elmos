# SYSTEM_RUNTIME_ESTIMATE — elmos-156-route-behavioural-equivalence

本报告只表示**系统自主**生成/转换、编译、测试、修复、恢复与打包所需的机器时间。

| 指标 | P50 | P80 | P90 | Worst Case |
|---|---|---|---|---|
| Wall-clock 小时 | 57.70 | 65.23 | 69.42 | 80.73 |
| Active worker 小时 | 179.25 | 202.41 | 216.29 | 251.68 |
| 关键路径小时 | 49.63 | 56.77 | 60.94 | 71.88 |

- 配置 Worker：12
- 有效并行容量：4.771（可用率 × 并行效率 × 模型并发 × 代码冲突系数）
- 全局开销系数：0.1
- P50 预计完成：2026-08-21T18:41:49.200000+08:00
- P90 预计完成：2026-08-22T06:25:04.800000+08:00

## 明确排除

- human approvals
- human acceptance and review effort
- credential and access provisioning waits
- external business or vendor decisions

> 这些排除项属于 `human_assisted` 口径，出现在对比报告里，绝不并入系统 ETA。
