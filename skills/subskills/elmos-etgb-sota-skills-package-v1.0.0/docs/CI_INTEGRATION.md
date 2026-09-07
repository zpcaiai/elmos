# CI integration

## Changed-based planning

`etgb plan --changed-from <base>` 根据变更路径选择 smoke 和受影响业务线 P0。生产集成应进一步使用：

- Semantic IR/规则/Skill 到 capability ID 的映射；
- dependency graph impact；
- 历史失败相似度；
- 风险模型；
- 仍保留随机未受影响抽样，检测错误影响分析。

## Sharding

稳定 shard key：`case_id + corpus_commit + target_stack`。同一 case 的随机 seeds 可并行，但结果在聚合前不得丢弃失败 seed。

## Artifact

每个 job 上传 JSONL result、日志、diff、trace、数据库快照摘要、性能、成本和环境 digest。聚合 job 验证证据完整性和 release gates。

## Flake

- 自动重跑只用于诊断；
- 首次失败仍计入 flake；
- P0 flake 阻断发布；
- quarantine 只能有 owner、原因、到期时间和替代 Oracle；
- 不允许无限重跑直到绿色。
