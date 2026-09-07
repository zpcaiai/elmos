# Release gates

## Hard gates

| Gate | 条件 |
|---|---|
| G-P0-PASS | P0 critical Oracle = 100% |
| G-P0-SSER | P0 SSER = 0 |
| G-DATA | Data corruption = 0 |
| G-SEC | Security regression = 0 |
| G-TX | P0 transaction mismatch = 0 |
| G-FLAKE | P0 flaky = 0 |
| G-P1 | P1 weighted pass ≥ 98.5% |
| G-P2 | P2 weighted pass ≥ 95% |
| G-CORPUS | 未批准语料 = 0 |
| G-EVIDENCE | 成功声明 evidence completeness = 100% |

## Gate precedence

硬门不可被平均分、业务压力或人工口头批准覆盖。例外只能通过正式 waiver：范围、理由、风险、补偿控制、负责人、到期时间和客户影响必须记录；P0 数据损坏、安全越权和 SSER 不允许 waiver。

## Candidate promotion

```text
commit → immutable image/skill/model digest
       → smoke
       → PR affected P0
       → nightly
       → full release
       → golden repositories
       → security/test/business owners sign
       → production canary
```

任何 digest 变化都使旧证据失效；仅文档变化可由变更分类规则豁免执行，但仍须通过 package integrity。
