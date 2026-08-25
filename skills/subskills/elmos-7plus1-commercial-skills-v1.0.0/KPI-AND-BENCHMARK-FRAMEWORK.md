# KPI 与 Benchmark Framework

## 1. 指标定义

### Accuracy

`verified-correct capabilities / evaluated capabilities`

必须按能力类型、风险和场景分层；仅 build pass 不计为行为正确。

### Completeness

`closed source-or-required capabilities / all discovered source-or-required capabilities`

状态必须单列：verified、tested、generated、mapped、blocked、unsupported、semantic_gap、unknown。

### Behavioral Equivalence

`passed differential scenarios / applicable differential scenarios`

同时报告 Critical mismatch、DB/cache/MQ/file/transaction/auth/exception/side-effect mismatch。

### Unknown Gap Rate

`high-risk capabilities without sufficient discovery/mapping/verification / all high-risk capabilities`

目标比“平均准确率”更关键；企业可以管理已知风险，难以管理未知风险。

### Automatic Repair Rate

`failures repaired and regression-verified without human code edits / eligible repair failures`

不把删除测试、改弱验收、重复 rerun 算修复。

## 2. 规划目标（不是当前实测）

| 指标 | Internal Beta 目标 | Commercial GA 目标 | E5 场景目标 |
| --- | ---: | ---: | ---: |
| Build success | ≥95% | ≥98% | ≥99% |
| Requirement closure | ≥90% | ≥96% | ≥98% |
| Capability closure | ≥90% | ≥96% | ≥98% |
| Behavioral equivalence | ≥88% | ≥94% | ≥97% |
| Critical unknown gaps | 0 | 0 | 0 |
| Automatic repair | ≥70% | ≥85% | ≥90% |
| Human intervention | ≤20% | ≤10% | ≤5–10% |
| False completion | <2% | <0.5% | 接近 0 |

上述值必须在具体矩阵上认证，不能对所有仓库、语言和行业做无条件承诺。

## 3. 对照实验

每次大版本至少比较：

1. 直接模型 + 基础 tools。
2. 通用 Harness（OpenCode/DeepSeek/OpenHarness 之一）。
3. Elmos Harness Runtime，但无 P02/P05/P07。
4. 完整 Elmos 7+1。

比较 Accuracy、Completeness、unknown gap、repair、cost、wall-clock ETA、人工介入和重复副作用。

## 4. Benchmark 分层

- Micro：语言语义/框架 API/规则单元。
- Component：API+DB、MQ、cache、auth、transaction、UI flow。
- Repository：10K/100K/1M+ LOC，多模块与 Monorepo。
- Migration：shadow/dual-run/cutover/rollback。
- Commercial：部署、SLA、安全、备份、DR、计费和客户验收。

## 5. 报告要求

报告版本、模型、Provider、Harness、规则、环境、源/目标 revision、样本量、失败详情、置信区间、成本与系统机器时间。不得只发布单一最好数字。
