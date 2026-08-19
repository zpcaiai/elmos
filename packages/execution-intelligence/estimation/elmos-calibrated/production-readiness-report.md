# PRODUCTION_READINESS_REPORT

- 证据目录：`estimation/elmos-calibrated`
- 结论：**block** — 有必需门禁执行后失败
- 通过 3 · 失败 3 · 未执行 4

| 门禁 | 内容 | 必需性 | 状态 | 说明 | 证据 |
|---|---|---|---|---|---|
| forecast-present | 存在可读的项目预测 | 必需 | ✅ PASS | token 分类互斥且 total 为分类之和 | project-forecast.json |
| confidence-is-supported | 声明的置信度不高于证据支撑的上限 | 必需 | ❌ FAIL | 声明 0.52，证据支撑上限 0.35；缺 运行时维度已用真实遥测校准（+0.15）；缺 运行时样本 >= 20（+0.10）；缺 token 维度已用真实用量校准（+0.20）；缺 token 样本 >= 20（+0.10）；缺 无待人工决策的范围缺口（+0.10）；缺 Chaos 场景全部执行并通过（+0.05）；缺 token 分类占比已对照实测用量（+0.05） | project-forecast.json |
| forecast-confidence | 预测置信度达到发布门槛 | 必需 | ❌ FAIL | confidence=0.52（门槛 0.6）；要在证据上支撑更高的置信度，还缺：没有校准记录 | project-forecast.json |
| eta-scope | 系统 ETA 明文排除人工等待 | 必需 | ✅ PASS | 排除项 4 条 | project-forecast.json |
| verified-rates | 费用基于已核验费率 | 可选 | ✅ PASS | 8 个可计费费率 | project-forecast.json |
| scope-gaps | 范围缺口已清零或已决策 | 必需 | ⛔ NOT_EXECUTED | risk-and-gap-register.json 不存在 | — |
| calibrated | 预测已用真实遥测校准 | 必需 | ⛔ NOT_EXECUTED | calibration.json 不存在；未校准的预测不构成承诺 | — |
| chaos-recovery | Chaos 与恢复验证通过 | 必需 | ⛔ NOT_EXECUTED | chaos-test-report.json 不存在 | — |
| artifacts-sealed | 结果 Manifest 已封存 | 必需 | ⛔ NOT_EXECUTED | result-manifest.json 不存在 | — |
| token-mix-verified | token 分类占比已对照实测 | 必需 | ❌ FAIL | 1 个会话（门槛 20），当前假设使费用偏离 5.51–10.90 倍 | token-mix-comparison.json |

> A gate with no evidence is NOT_EXECUTED, never PASS. 'release' requires every required gate to have executed and passed; anything else is 'not_certified' or 'block'.
