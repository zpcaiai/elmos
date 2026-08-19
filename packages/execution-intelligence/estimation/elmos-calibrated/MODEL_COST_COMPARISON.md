# MODEL_COST_COMPARISON — elmos-156-route-behavioural-equivalence

- 费率注册表版本：`2026-08-19-verified-list-prices`
- 基准币种：`USD`，出现的币种：USD
- 对应 Token 总量 P50：795,559,011，P90：909,753,569

## 1. 各方案费用区间

| 方案 | model_id | 供应商 | 币种 | P50 | P80 | P90 | Worst | 费率状态 |
|---|---|---|---|---|---|---|---|---|
| Claude Opus 5 | anthropic-opus-5 | anthropic | USD | 2,641.7244 | 2,874.9757 | 3,013.5856 | 3,367.8340 | 已核验 |
| Claude Sonnet 5 | anthropic-sonnet-5 | anthropic | USD | 1,056.6897 | 1,149.9903 | 1,205.4342 | 1,347.1336 | 已核验 |
| Claude Haiku 4.5 | anthropic-haiku-4-5 | anthropic | USD | 528.3449 | 574.9951 | 602.7171 | 673.5668 | 已核验 |
| gpt-5.6-sol (short context) | openai-gpt-5-6-sol | openai | USD | 1,253.8568 | 1,363.8141 | 1,430.5374 | 1,599.4582 | 已核验 |
| gpt-5.6-terra (short context) | openai-gpt-5-6-terra | openai | USD | 501.5427 | 545.5256 | 572.2150 | 639.7833 | 已核验 |
| gpt-5.6-luna (short context) | openai-gpt-5-6-luna | openai | USD | 50.1543 | 54.5526 | 57.2215 | 63.9783 | 已核验 |
| deepseek-v4-pro (peak hours) | deepseek-v4-pro-peak | deepseek | USD | 446.9484 | 486.4556 | 509.9620 | 570.3299 | 已核验 |
| deepseek-v4-flash (peak hours) | deepseek-v4-flash-peak | deepseek | USD | 148.6453 | 161.7818 | 169.6070 | 189.6773 | 已核验 |

## 2. 费用构成（按类别占比，均值口径）

| 方案 | input | cached_input | cache_write | output | reasoning_output |
|---|---|---|---|---|---|
| Claude Opus 5 | 36.4% | 9.6% | 13.2% | 25.2% | 15.6% |
| Claude Sonnet 5 | 36.4% | 9.6% | 13.2% | 25.2% | 15.6% |
| Claude Haiku 4.5 | 36.4% | 9.6% | 13.2% | 25.2% | 15.6% |
| gpt-5.6-sol (short context) | 38.4% | 10.1% | 0.0% | 31.9% | 19.7% |
| gpt-5.6-terra (short context) | 38.4% | 10.1% | 0.0% | 31.9% | 19.7% |
| gpt-5.6-luna (short context) | 38.4% | 10.1% | 0.0% | 31.9% | 19.7% |
| deepseek-v4-pro (peak hours) | 56.8% | 5.0% | 0.0% | 23.6% | 14.6% |
| deepseek-v4-flash (peak hours) | 57.0% | 4.8% | 0.0% | 23.6% | 14.6% |

> 缓存命中率直接决定 `cached_input` 这一列的权重。它是这张表里最容易被高估的一项：
> 预测里的命中率是假设值，执行后必须用真实 usage 校准。

## 3. 同币种排序

| 币种 | 按 P50 从便宜到贵 | 最便宜 | 排序池 |
|---|---|---|---|
| USD | openai-gpt-5-6-luna, deepseek-v4-flash-peak, deepseek-v4-pro-peak, openai-gpt-5-6-terra, anthropic-haiku-4-5, anthropic-sonnet-5, openai-gpt-5-6-sol, anthropic-opus-5 | openai-gpt-5-6-luna | verified_rates |

> Models priced in different currencies are never ranked against each other here. Supply a dated FX rate and do that conversion explicitly if it is needed.

## 4. 费率溯源

| model_id | 生效日期 | 核验时间 | 计费模式 | 来源 |
|---|---|---|---|---|
| anthropic-opus-5 | 2026-08-19 | 2026-08-19T00:00:00Z | api | https://platform.claude.com/docs/en/about-claude/pricing |
| anthropic-sonnet-5 | 2026-08-19 | 2026-08-19T00:00:00Z | api | https://platform.claude.com/docs/en/about-claude/pricing |
| anthropic-haiku-4-5 | 2026-08-19 | 2026-08-19T00:00:00Z | api | https://platform.claude.com/docs/en/about-claude/pricing |
| openai-gpt-5-6-sol | 2026-08-19 | 2026-08-19T00:00:00Z | api | https://developers.openai.com/api/docs/pricing |
| openai-gpt-5-6-terra | 2026-08-19 | 2026-08-19T00:00:00Z | api | https://developers.openai.com/api/docs/pricing |
| openai-gpt-5-6-luna | 2026-08-19 | 2026-08-19T00:00:00Z | api | https://developers.openai.com/api/docs/pricing |
| deepseek-v4-pro-peak | 2026-08-19 | 2026-08-19T00:00:00Z | api | https://api-docs.deepseek.com/quick_start/pricing |
| deepseek-v4-flash-peak | 2026-08-19 | 2026-08-19T00:00:00Z | api | https://api-docs.deepseek.com/quick_start/pricing |

> Any model marked not_for_billing uses illustrative rates. It validates the arithmetic only and must not back a financial commitment.

> 本包不写死任何厂商价格。要得到可用于预算的数字，把已核验费率填进
> `config/model-pricing.json`（从 `model-pricing.template.json` 复制），`null` 不填校验会拒绝。
