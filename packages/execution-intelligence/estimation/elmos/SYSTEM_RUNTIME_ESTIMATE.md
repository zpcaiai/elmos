# SYSTEM_RUNTIME_ESTIMATE — elmos

本报告只表示**系统自主**生成/转换、编译、测试、修复、恢复与打包所需的机器时间。

| 指标 | P50 | P80 | P90 | Worst Case |
|---|---|---|---|---|
| Wall-clock 小时 | 56.65 | 64.04 | 68.16 | 79.27 |
| Active worker 小时 | 175.99 | 198.73 | 212.36 | 247.10 |
| 关键路径小时 | 48.72 | 55.74 | 59.83 | 70.57 |

- 配置 Worker：9
- 有效并行容量：4.307（可用率 × 并行效率 × 模型并发 × 代码冲突系数）
- 全局开销系数：0.08
- P50 预计完成：未配置 system.start_at
- P90 预计完成：未配置 system.start_at

## 明确排除

- human approvals
- human acceptance and review effort
- credential and access provisioning waits
- external business or vendor decisions

> 这些排除项属于 `human_assisted` 口径，出现在对比报告里，绝不并入系统 ETA。
