# 必须在 CI/预生产执行的并发与故障测试

`invariants.sql` 能检查静态与现有数据不变量，但以下测试需要多个并发连接、真实 PostgreSQL 和故障注入。

## 1. 三槽并发

- 创建一个 concurrency_limit=3 的账号；
- 100 个连接同时调用 `core.claim_account_slot`；
- 恰好最多 3 个成功；
- 其余返回无槽，不产生额外 Run；
- 释放后下一批可以 Claim；
- generation 单调递增。

## 2. 幂等提交

- 50 个并发连接使用同一个 idempotency key + request hash；
- 只产生一个 `job_submission` 和一个 Job；
- 所有调用返回同一 Job；
- 同键不同 hash 返回冲突。

## 3. Lease Fencing

- Worker A Claim generation=N；
- 停止续租，让 Lease 过期；
- Worker B Claim generation=N+1；
- A 调用 finish，必须得到 STALE_FENCE；
- B finish 成功；
- Task 输出只绑定 B 的 Manifest。

## 4. Event 并发追加

- 50 个连接向同一 Run 调用 `exec.append_run_event`；
- sequence 连续且唯一；
- previous_event_hash 链正确；
- cursor=max(sequence)+1。

## 5. Outbox 崩溃窗口

- 业务事务提交 Outbox 后、发布前杀死进程；
- Relay 重启后发布；
- 发布成功但 mark published 前杀死 Relay；
- 消费者 Inbox 去重，业务结果只生效一次。

## 6. Side-effect Unknown Result

- Provider 接收请求并成功，但客户端超时；
- Receipt 转 `unknown_result`；
- 系统不能立即重复写；
- Reconciler 查询 external operation 后转 succeeded；
- P05 在 reconciliation 前拒绝完成，之后可继续。

## 7. Checkpoint 崩溃

- 组件上传一半时杀死 Worker；
- Checkpoint 不能 sealed；
- 恢复器回退前一个 sealed Checkpoint；
- 未完成 staged object 被续传或 GC。

## 8. PostgreSQL Failover

在 Claim、Event Append、Attempt Finish、P05 Complete 的 COMMIT 临界点触发主备切换：

- 客户端不知道结果时以同一幂等键重试；
- 最终状态只能是一次提交或一次未提交；
- 不出现重复槽、重复 Attempt 结果、事件 gap、双重成本分录。

## 9. P05 竞态

- Gate pass 后并发新增 critical gap/撤销 Evidence/产生 unknown side effect；
- `verify.complete_run_with_gate` 必须在自己的事务快照与锁语义下重新验证；
- 不允许基于陈旧应用层查询完成。

## 10. RLS 双租户

两个连接分别设置 Tenant A/B：

- 所有表、视图、事务函数均不能跨租户；
- 无 tenant context 时 fail closed；
- 表 owner 之外应用角色也不能 bypass RLS。
