# Operations runbook

## Run preparation

- 固定 release candidate 的 model/skill/toolchain/image digest；
- 检查语料许可证和 commit；
- 检查容量、并发、预算和隔离；
- 清除非可信缓存或验证 cache provenance；
- 生成 run ID 和 shard plan。

## During run

- 监控队列、P95 case duration、失败类型、资源、token/credit、cache hit；
- 基础设施异常可按策略重试；产品失败不自动重试抹除；
- 发现数据/安全问题立即停止相关业务线和发布；
- 保留失败 workspace 的只读快照，先脱敏再授权访问。

## After run

- 聚合结果与 evidence；
- 运行 gate；
- 聚类失败根因；
- 每个新缺陷创建 regression case；
- 签名 evidence bundle；
- 记录决定：promote、reject 或正式 waiver。

## Incident

若生产发现静默语义错误：

1. 冻结相关版本和规则；
2. 确认客户/数据/安全影响；
3. 从真实输入构造最小+回放 case；
4. 添加 hidden test 和 mutant；
5. 修复后跑受影响矩阵、release 和 Golden Route；
6. 更新 SSER 和事故复盘。
