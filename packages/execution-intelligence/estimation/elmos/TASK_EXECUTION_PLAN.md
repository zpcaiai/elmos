# TASK_EXECUTION_PLAN — elmos-156-route-behavioural-equivalence

- Run ID：`not-yet-submitted`
- DAG：`elmos-156-route-behavioural-equivalence`，任务数 16
- 有效并行容量：4.771（配置 Worker 12）
- 完成定义：`production_verified`
- 生成时间：unset

## 执行波次

| 波次 | 任务数 | 任务 | 并发 worker units |
|---|---|---|---|
| 1 | 1 | matrix-authority-audit | 1.0 |
| 2 | 4 | analyzer-cache-batch, flutter-analyzer, kotlin-analyzer, react-analyzer | 7.0 |
| 3 | 2 | repo-parallel-singlepass, route-packs-66 | 5.0 |
| 4 | 1 | semantic-divergence | 2.0 |
| 5 | 2 | java-swift-regression, matrix-small | 6.0 |
| 6 | 1 | matrix-medium | 4.0 |
| 7 | 3 | frozen-rerun-evidence, perf-baseline, security-license | 6.0 |
| 8 | 1 | independent-client-repos | 3.0 |
| 9 | 1 | certification-package | 1.0 |

## 关键路径

matrix-authority-audit → kotlin-analyzer → route-packs-66 → semantic-divergence → matrix-small → matrix-medium → frozen-rerun-evidence → independent-client-repos → certification-package

关键路径长度（P50 口径）：6380.0 分钟。加人不能压缩这条链。

## 每个任务的恢复策略

| 任务 | 失败概率 | 恢复分钟 乐观/最可能/悲观 | 返工概率 |
|---|---|---|---|
| matrix-authority-audit | 0.02 | 3/12/60 | 0.1 |
| kotlin-analyzer | 0.15 | 3/12/60 | 0.3 |
| react-analyzer | 0.15 | 3/12/60 | 0.3 |
| flutter-analyzer | 0.15 | 3/12/60 | 0.3 |
| route-packs-66 | 0.1 | 3/12/60 | 0.25 |
| semantic-divergence | 0.08 | 3/12/60 | 0.28 |
| analyzer-cache-batch | 0.06 | 3/12/60 | 0.2 |
| repo-parallel-singlepass | 0.08 | 3/12/60 | 0.22 |
| java-swift-regression | 0.12 | 3/12/60 | 0.3 |
| matrix-small | 0.18 | 10/30/120 | 0.25 |
| matrix-medium | 0.22 | 15/45/180 | 0.3 |
| frozen-rerun-evidence | 0.2 | 15/45/180 | 0.18 |
| independent-client-repos | 0.25 | 20/60/240 | 0.35 |
| security-license | 0.05 | 3/12/60 | 0.15 |
| perf-baseline | 0.08 | 3/12/60 | 0.18 |
| certification-package | 0.04 | 3/12/60 | 0.15 |

## 明确排除

- 人工审批
- 人工验收与复核
- 凭据与访问开通等待
- 外部业务或供应商决策

> 本计划只描述机器自主执行。人工审批与验收时间不在其中。
