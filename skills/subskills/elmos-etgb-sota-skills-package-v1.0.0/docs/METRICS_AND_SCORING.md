# Metrics and scoring

## 1. 不合并为一个虚假的总分

Dashboard 应分别显示：

- build/test pass；
- behavior equivalence；
- state/transaction equivalence；
- security；
- performance；
- SSER；
- HIR；
- evidence completeness；
- cost/wall-clock。

单一总分仅用于排序，不能覆盖硬门。

## 2. 计算

- P0 权重 5、P1 权重 2、P2 权重 1；
- skipped/unavailable 单列，不从失败改写为通过；
- infrastructure retry 与产品 retry 分开；
- 只对确定的基础设施错误允许自动重试一次；
- 测试失败重跑后通过仍标记 flaky，不能抹掉首次失败。

## 3. SSER

“成功声明”发生在 Elmos 返回 success 或发布产物后。若隐藏/独立 Oracle 之后发现语义错误，则计入 SSER。主动拒绝、不支持或人工审批不计入 SSER，但计入 HIR/unsupported rate。

## 4. Cost

每个 case 记录：input/output/cached token、provider credit、工具 CPU/内存/磁盘/网络、wall-clock、重试、缓存命中、人工审批时间。客户报价与 ETA 应由同类历史分布校准，不使用人工人天替代机器运行时长。
