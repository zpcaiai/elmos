# MODEL_ROUTING_COMPARISON

- 币种：`USD`（只在同一币种内优化）
- 全 frontier 基线模型：`openai-gpt-5-6-sol`
- 分层分布：{'frontier': 8, 'mid': 5}

## 总量

| 方案 | 费用 |
|---|---|
| 全 frontier 基线 | 1,114.8161 |
| 能力约束下的最优路由 | 1,010.0215 |
| 节省 | 104.7946（9.4%） |

## 每个任务的路由

| 任务 | 复杂度 | 能力下限 | 分配模型 | 费用 | frontier 基线 | 节省 |
|---|---|---|---|---|---|---|
| scope-authority-audit | medium | mid | deepseek-v4-pro-peak | 7.2177 | 20.5512 | 13.3335 |
| analyzer-flutter | high | frontier | openai-gpt-5-6-sol | 69.1178 | 69.1178 | 0.0000 |
| analyzer-kotlin | high | frontier | openai-gpt-5-6-sol | 69.1178 | 69.1178 | 0.0000 |
| analyzer-react | high | frontier | openai-gpt-5-6-sol | 69.1178 | 69.1178 | 0.0000 |
| route-packs | high | frontier | openai-gpt-5-6-sol | 107.4060 | 107.4060 | 0.0000 |
| semantic-divergence | high | frontier | openai-gpt-5-6-sol | 107.6049 | 107.6049 | 0.0000 |
| analyzer-performance | medium | mid | deepseek-v4-pro-peak | 11.9335 | 33.9787 | 22.0453 |
| matrix-small | high | frontier | openai-gpt-5-6-sol | 111.5166 | 111.5166 | 0.0000 |
| matrix-medium | high | frontier | openai-gpt-5-6-sol | 209.3754 | 209.3754 | 0.0000 |
| frozen-rerun-evidence | medium | mid | deepseek-v4-pro-peak | 18.0224 | 51.3162 | 33.2938 |
| independent-client-verification | high | frontier | openai-gpt-5-6-sol | 210.0384 | 210.0384 | 0.0000 |
| security-license | medium | mid | deepseek-v4-pro-peak | 6.7235 | 19.1441 | 12.4206 |
| certification-package | medium | mid | deepseek-v4-pro-peak | 12.8299 | 36.5313 | 23.7014 |

## 上下文窗口约束

- 已强制：13 个任务
- 未声明 `peak_context_tokens`、无法检查：0 个任务

> A model is only eligible when its max_context_tokens covers the task's declared peak_context_tokens. Tasks that declare no peak are listed here rather than being assumed to fit.

## 注意

- Routing assumes the cheaper tier actually completes the task; if it fails and escalates, the retry cost eats the saving. Verify escalation rate before trusting the number.
- Costs use point token estimates (P50-equivalent), not the full distribution.
