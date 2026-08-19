# MODEL_ROUTING_COMPARISON

- 币种：`USD`（只在同一币种内优化）
- 全 frontier 基线模型：`openai-gpt-5-6-sol`
- 分层分布：{'frontier': 9, 'mid': 7}

## 总量

| 方案 | 费用 |
|---|---|
| 全 frontier 基线 | 902.6000 |
| 能力约束下的最优路由 | 773.6052 |
| 节省 | 128.9948（14.3%） |

## 每个任务的路由

| 任务 | 复杂度 | 能力下限 | 分配模型 | 费用 | frontier 基线 | 节省 |
|---|---|---|---|---|---|---|
| matrix-authority-audit | medium | mid | deepseek-v4-pro-peak | 5.3240 | 14.1000 | 8.7760 |
| kotlin-analyzer | high | frontier | openai-gpt-5-6-sol | 69.2500 | 69.2500 | 0.0000 |
| react-analyzer | high | frontier | openai-gpt-5-6-sol | 64.0000 | 64.0000 | 0.0000 |
| flutter-analyzer | high | frontier | openai-gpt-5-6-sol | 66.7000 | 66.7000 | 0.0000 |
| route-packs-66 | high | frontier | openai-gpt-5-6-sol | 106.0000 | 106.0000 | 0.0000 |
| semantic-divergence | high | frontier | openai-gpt-5-6-sol | 87.2500 | 87.2500 | 0.0000 |
| analyzer-cache-batch | medium | mid | deepseek-v4-pro-peak | 12.2672 | 34.5500 | 22.2828 |
| repo-parallel-singlepass | medium | mid | deepseek-v4-pro-peak | 13.6400 | 38.3750 | 24.7350 |
| java-swift-regression | medium | frontier | openai-gpt-5-6-sol | 50.5000 | 50.5000 | 0.0000 |
| matrix-small | high | frontier | openai-gpt-5-6-sol | 43.7500 | 43.7500 | 0.0000 |
| matrix-medium | high | frontier | openai-gpt-5-6-sol | 81.5000 | 81.5000 | 0.0000 |
| frozen-rerun-evidence | medium | mid | deepseek-v4-pro-peak | 11.9768 | 34.2000 | 22.2232 |
| independent-client-repos | high | frontier | openai-gpt-5-6-sol | 134.0000 | 134.0000 | 0.0000 |
| security-license | medium | mid | deepseek-v4-pro-peak | 7.4096 | 20.7750 | 13.3654 |
| perf-baseline | medium | mid | deepseek-v4-pro-peak | 8.8616 | 24.9000 | 16.0384 |
| certification-package | medium | mid | deepseek-v4-pro-peak | 11.1760 | 32.7500 | 21.5740 |

## 上下文窗口约束

- 已强制：0 个任务
- 未声明 `peak_context_tokens`、无法检查：16 个任务

> A model is only eligible when its max_context_tokens covers the task's declared peak_context_tokens. Tasks that declare no peak are listed here rather than being assumed to fit.

## 注意

- Routing assumes the cheaper tier actually completes the task; if it fails and escalates, the retry cost eats the saving. Verify escalation rate before trusting the number.
- Costs use point token estimates (P50-equivalent), not the full distribution.
- 16 task(s) declare no peak_context_tokens, so the context window constraint could not be checked for them.
