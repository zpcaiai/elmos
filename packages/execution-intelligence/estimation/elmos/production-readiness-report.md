# PRODUCTION_READINESS_REPORT

- 证据目录：`estimation/elmos`
- 结论：**block** — 有必需门禁执行后失败
- 通过 9 · 失败 2 · 未执行 0

| 门禁 | 内容 | 必需性 | 状态 | 说明 | 证据 |
|---|---|---|---|---|---|
| forecast-present | 存在可读的项目预测 | 必需 | ✅ PASS | token 分类互斥且 total 为分类之和 | project-forecast.json |
| confidence-is-supported | 声明的置信度不高于证据支撑的上限 | 必需 | ✅ PASS | 声明 0.6，证据支撑上限 0.65；缺 运行时样本 >= 20（+0.10）；缺 token 维度已用真实用量校准（+0.20）；缺 token 样本 >= 20（+0.10）；缺 token 分类占比已对照实测用量（+0.05） | project-forecast.json |
| forecast-confidence | 预测置信度达到发布门槛 | 必需 | ✅ PASS | confidence=0.6（门槛 0.6） | project-forecast.json |
| eta-scope | 系统 ETA 明文排除人工等待 | 必需 | ✅ PASS | 排除项 4 条 | project-forecast.json |
| verified-rates | 费用基于已核验费率 | 可选 | ✅ PASS | 8 个可计费费率 | project-forecast.json |
| scope-gaps | 范围缺口已清零或已决策 | 必需 | ✅ PASS | 无待决缺口 | risk-and-gap-register.json |
| calibrated | 预测已用真实遥测校准 | 必需 | ❌ FAIL | 3 个有效样本（门槛 20） | calibration.json |
| chaos-recovery | Chaos 与恢复验证通过 | 必需 | ✅ PASS | 5 个场景，0 个失败 | chaos-test-report.json |
| artifacts-sealed | 结果 Manifest 已封存 | 必需 | ✅ PASS | sealed=True，artifact 16 个 | result-manifest.json |
| token-mix-verified | token 分类占比已对照实测 | 必需 | ❌ FAIL | 1 个会话（门槛 20），当前假设使费用偏离 1.17 倍（5 轮任务）到 5.54 倍（800 轮），随任务长度变化 | token-mix-comparison.json |
| routing-complete | 每个任务都有可用模型 | 可选 | ✅ PASS | 全部任务可路由 | model-routing-plan.json |

> A gate with no evidence is NOT_EXECUTED, never PASS. 'release' requires every required gate to have executed and passed; anything else is 'not_certified' or 'block'.
