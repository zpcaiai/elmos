# 失败分类

重试策略按**分类**选，不按异常文本选。文本匹配会在依赖升级换了措辞的那天静默失效。

| 分类 | 判据 | 策略 | 典型 |
| --- | --- | --- | --- |
| `transient` | 重跑同一请求有合理概率成功 | 指数退避 + 抖动，上限内重试 | 限流、超时、网络抖动、临时磁盘不足 |
| `permanent` | 重跑必然同样失败 | 不重试，标记 failed 并上报 | 编译错误、断言失败、契约不匹配、参数非法 |
| `business_conflict` | 需要决策而不是重试 | 挂起等待人工或上游决策 | 冻结集变更、许可证冲突、并发写入冲突 |
| `lost_worker` | 尝试没有结论，心跳超时 | 先核对四步，再决定接管 | 容器被杀、主机重启、进程 OOM |

## `lost_worker` 不等于失败

心跳超时只说明**这个 Worker 不再报告**，不说明工作没做完。它可能已经提交了 commit、
发布了 artifact，甚至已经完成但没来得及写状态。把它当 `permanent` 处理会丢结果，
当 `transient` 直接重试会产生重复副作用。正确做法是走 `state-machine.md` 的四步核对。

## 磁盘不足是 `transient` 还是 `permanent`

取决于余量能否恢复。清理后能继续的是 `transient`；配额本身不够的是 `permanent`。
编排器不该自己猜——把阈值写进重试策略配置，让判据可审计。

## 记录要求

每个尝试至少落库：`task_id`、`step_id`、`attempt`、`worker_id`、`failure_class`、
`queue_ms`、`execution_ms`、`build_ms`、`test_ms`、`recovery_ms`、`outcome`。
没有 `failure_class` 的失败记录，事后无法做重试策略调优。
