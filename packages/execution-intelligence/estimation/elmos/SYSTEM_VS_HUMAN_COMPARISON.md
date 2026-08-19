# SYSTEM_VS_HUMAN_COMPARISON — elmos

## 同一完成定义

- Level：`production_verified`
- Checks：source-compiles, unit-tests, integration-tests, behavioral-equivalence, security-and-license-scan, performance-baseline, evidence-recorded

## 三套时间

| 方案 | P50 | P90 | 口径 |
|---|---|---|---|
| 系统自主 | 56.65 小时 | 68.16 小时 | 机器连续 Wall-clock，不含任何人工等待 |
| 纯人工 | 42.83 周 | 46.27 周 | 配置团队 + 工作日历 + 同等 DoD |
| 人机协作端到端 | 56.65 小时 | 68.16 小时 | 系统 + 不可并行的人工复核 + 审批/外部等待 |

## 对比结论

- P50 日历加速：**127.01×**
- P90 日历加速：**114.04×**
- 人工投入减少：**100.00%**
- P50 节省人工：**6,815.23 人时**
- 自动化覆盖：**100.00%**
- 置信度：**0.6**

> 口径提醒：Human calendar weeks include nights and weekends; the system figure is continuous machine time.

## 模型费用场景

| 模型 | 币种 | P50 | P80 | P90 | Worst | 费率状态 |
|---|---|---|---|---|---|---|
| Claude Opus 5 | USD | 2,641.7244 | 2,874.9757 | 3,013.5856 | 3,367.8340 | 已核验 2026-08-19T00:00:00Z |
| Claude Sonnet 5 | USD | 1,056.6897 | 1,149.9903 | 1,205.4342 | 1,347.1336 | 已核验 2026-08-19T00:00:00Z |
| Claude Haiku 4.5 | USD | 528.3449 | 574.9951 | 602.7171 | 673.5668 | 已核验 2026-08-19T00:00:00Z |
| gpt-5.6-sol (short context) | USD | 1,253.8568 | 1,363.8141 | 1,430.5374 | 1,599.4582 | 已核验 2026-08-19T00:00:00Z |
| gpt-5.6-terra (short context) | USD | 501.5427 | 545.5256 | 572.2150 | 639.7833 | 已核验 2026-08-19T00:00:00Z |
| gpt-5.6-luna (short context) | USD | 50.1543 | 54.5526 | 57.2215 | 63.9783 | 已核验 2026-08-19T00:00:00Z |
| deepseek-v4-pro (peak hours) | USD | 446.9484 | 486.4556 | 509.9620 | 570.3299 | 已核验 2026-08-19T00:00:00Z |
| deepseek-v4-flash (peak hours) | USD | 148.6453 | 161.7818 | 169.6070 | 189.6773 | 已核验 2026-08-19T00:00:00Z |

| 币种 | 按 P50 排序 | 排序池 |
|---|---|---|
| USD | openai-gpt-5-6-luna, deepseek-v4-flash-peak, deepseek-v4-pro-peak, openai-gpt-5-6-terra, anthropic-haiku-4-5, anthropic-sonnet-5, openai-gpt-5-6-sol, anthropic-opus-5 | verified_rates |

> Models priced in different currencies are never ranked against each other here. Supply a dated FX rate and do that conversion explicitly if it is needed.

> Any model marked not_for_billing uses illustrative rates. It validates the arithmetic only and must not back a financial commitment.

## 假设与排除项

- 假设：Seeded by the scope auditor from measured repository facts plus configured defaults.
- 假设：Durations and token profiles are seeds, not measurements; calibrate after the first milestone.
- 排除：Human approval and acceptance time (carried in human_assisted).
- 排除：Vendor pricing (supply a verified rate card).
