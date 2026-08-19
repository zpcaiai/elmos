# FORECAST_ACCURACY_REPORT

- 有效样本：3（运行时 3 · Token 0），丢弃：0
- 全局置信度：0.41

## 全局偏差

| 维度 | P50 倍率 | P80 | P90 | 结论 |
|---|---|---|---|---|
| 运行时 | 0.263 | 0.338 | 0.363 | **高估 73.7%** |
| Token | 无数据 | 无数据 | 无数据 | **无数据**（不推断倍率） |

> 倍率的定义是 `实际 / 预测`。大于 1 表示预测偏低。

> 无数据的维度：token: no row carried a positive estimated/actual token pair

## 分组倍率

| 分组 (task_type / complexity / model) | 样本 | 运行时 P50 | Token P50 | 置信度 | 可用 |
|---|---|---|---|---|---|
| verification / high / not-a-model-run | 3 | 0.263 | 无数据 | 0.500 | 否 |

> Use a group multiplier only when that group has at least 5 samples (applicable=true); otherwise fall back to the global multiplier and keep the wider interval.

## 将被应用的 estimator profiles

- 默认（全局）：运行时 ×0.263（实测），Token ×1.0（无数据，不改写）
- 可用分组数：0

## 丢弃的样本

- 无

> 丢弃的行不会被补全或猜测。预测与实测缺任一侧的记录一律不参与倍率计算。
