# SYSTEM_VS_HUMAN_COMPARISON — elmos-156-route-behavioural-equivalence

## 同一完成定义

- Level：`production_verified`
- Checks：source-compiles, unit-tests, integration-tests, behavioral-equivalence-small, behavioral-equivalence-medium, frozen-matrix-rerun, independent-client-repository-verification, security-and-license-scan, performance-baseline, evidence-recorded-in-TEST_RESULTS-and-EVIDENCE

## 三套时间

| 方案 | P50 | P90 | 口径 |
|---|---|---|---|
| 系统自主 | 57.70 小时 | 69.42 小时 | 机器连续 Wall-clock，不含任何人工等待 |
| 纯人工 | 44.80 周 | 48.40 周 | 配置团队 + 工作日历 + 同等 DoD |
| 人机协作端到端 | 145.70 小时 | 157.42 小时 | 系统 + 不可并行的人工复核 + 审批/外部等待 |

## 对比结论

- P50 日历加速：**130.46×**
- P90 日历加速：**117.13×**
- 人工投入减少：**98.24%**
- P50 节省人工：**6,695.23 人时**
- 自动化覆盖：**98.24%**
- 置信度：**0.52**

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

- 假设：路由分母以 routes/inventory.json 为唯一权威：156 条有向路线、13 门语言。
- 假设：kotlin / react / flutter 三门语言的 analyzer 仍是 PENDING_ANALYZER，需要从零补齐并钉死工具链。
- 假设：工具链沿用 symlink-free 钉版契约，不引入包管理器的全局安装。
- 假设：系统 Worker 可 24×7 连续运行，中断后能从 Checkpoint 恢复。
- 假设：任务时长与 token 画像是工程估计而非实测，首个里程碑执行完必须用 calibrate 回填。
- 假设：code_conflict_factor 取 0.82，反映多个 Agent 在同一棵树上写入的真实冲突代价。
- 假设：配置 12 个 Agent Worker，在可用率、并行效率、模型并发与代码冲突系数之后有效并发约 4.8，必须不小于单个任务声明的 worker_units 上限（4）。
- 排除：人工审批与验收时间（计入 human_assisted，不计入系统 ETA）
- 排除：外部客户提供仓库与授权的等待时间
- 排除：认证机构排期
- 排除：真实厂商价格（价格来自可配置费率表，本包不写死）
