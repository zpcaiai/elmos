# RECOVERY_EVIDENCE

- 项目：`elmos-156-route-behavioural-equivalence`
- 场景：执行 5 · 通过 5 · 失败 0 · 未执行 0
- 总体：通过

# INCIDENT_RECOVERY_REPORT — worker-killed-mid-task

- 场景：worker-killed-mid-task
- 注入时刻：t0
- 检测耗时：120000 ms
- 恢复耗时：1000 ms

## 发生了什么

第二个任务的 Worker 在执行中消失，未写回任何结论。心跳超时后被判定为 lost_worker，经四步核对后重试，最终整条 DAG 完成。

## 恢复前的四步核对

| 检查 | 结果 | 依据 |
| --- | --- | --- |
| 原请求（幂等键） | completed | idempotency_key 表 |
| 原 Commit | absent | checkpoint.git_commit |
| 原 Artifact | absent | artifact (run, logical_name, sha256) |
| 失败分类 | adopt_existing_result | task_attempt.failure_class |

## 断言结果

- ✅ interrupted attempt stayed open for the sweeper：`1`
- ✅ lost attempt classified as lost_worker, not failed：`['c1']`
- ✅ completed work was not redone：`['c0']`
- ✅ run reached succeeded after recovery：`succeeded`
- ✅ c1 was retried exactly once：`2`

## 遗留影响

无。c0 未重跑，c1 只重试一次。

> 没有执行过的检查记为「未执行」，不记为「通过」。


# INCIDENT_RECOVERY_REPORT — orchestrator-restart

- 场景：orchestrator-restart
- 注入时刻：t0
- 检测耗时：0 ms
- 恢复耗时：0 ms

## 发生了什么

编排器进程在两个任务之后重启。新进程只从存储恢复状态，不持有任何内存状态，因此继续执行剩余任务而没有重跑已完成的部分。

## 恢复前的四步核对

| 检查 | 结果 | 依据 |
| --- | --- | --- |
| 原请求（幂等键） | n/a | idempotency_key 表 |
| 原 Commit | n/a | checkpoint.git_commit |
| 原 Artifact | n/a | artifact (run, logical_name, sha256) |
| 失败分类 | n/a | task_attempt.failure_class |

## 断言结果

- ✅ no task executed twice across the restart：`['c0', 'c1', 'c2', 'c3']`
- ✅ work completed before the restart was preserved：`['c0', 'c1']`
- ✅ run completed after the restart：`succeeded`

## 遗留影响

无。

> 没有执行过的检查记为「未执行」，不记为「通过」。


# INCIDENT_RECOVERY_REPORT — client-disconnect-and-reconnect

- 场景：client-disconnect-and-reconnect
- 注入时刻：t0
- 检测耗时：0 ms
- 恢复耗时：0 ms

## 发生了什么

客户端在第一个任务后断开，运行继续。重连时带 Last-Event-ID，服务端回放其错过的全部事件，序号连续、无重复。

## 恢复前的四步核对

| 检查 | 结果 | 依据 |
| --- | --- | --- |
| 原请求（幂等键） | n/a | idempotency_key 表 |
| 原 Commit | n/a | checkpoint.git_commit |
| 原 Artifact | n/a | artifact (run, logical_name, sha256) |
| 失败分类 | n/a | task_attempt.failure_class |

## 断言结果

- ✅ replay is gapless from the last seen sequence：`[8, 9, 10, 11, 12]`
- ✅ no already-seen event is redelivered：`7`
- ✅ nothing produced while disconnected was dropped：`{'seen': 7, 'replayed': 17, 'total': 24}`
- ✅ execution continued while the client was gone：`17`

## 遗留影响

无。事件流是仅追加的，断连不影响执行。

> 没有执行过的检查记为「未执行」，不记为「通过」。


# INCIDENT_RECOVERY_REPORT — duplicate-submission

- 场景：duplicate-submission
- 注入时刻：t0
- 检测耗时：0 ms
- 恢复耗时：0 ms

## 发生了什么

同一批工作被重复提交。幂等键命中已完成记录，直接返回原响应；重复发布相同字节的 Artifact 被内容寻址去重，没有产生新版本。

## 恢复前的四步核对

| 检查 | 结果 | 依据 |
| --- | --- | --- |
| 原请求（幂等键） | completed | idempotency_key 表 |
| 原 Commit | present | checkpoint.git_commit |
| 原 Artifact | present | artifact (run, logical_name, sha256) |
| 失败分类 | adopt_existing_result | task_attempt.failure_class |

## 断言结果

- ✅ every duplicate submission replayed instead of re-executing：`['replayed', 'replayed', 'replayed', 'replayed']`
- ✅ no additional side effect ran：`4`
- ✅ republishing identical bytes did not create a new artifact version：`1`

## 遗留影响

无。副作用只发生一次。

> 没有执行过的检查记为「未执行」，不记为「通过」。


# INCIDENT_RECOVERY_REPORT — idempotency-key-misuse

- 场景：idempotency-key-misuse
- 注入时刻：t0
- 检测耗时：0 ms
- 恢复耗时：0 ms

## 发生了什么

同一个幂等键被配上不同的请求体。服务端拒绝而不是把旧响应发给一个不同的请求——后者会产生几乎无法排查的错误结果。

## 恢复前的四步核对

| 检查 | 结果 | 依据 |
| --- | --- | --- |
| 原请求（幂等键） | completed | idempotency_key 表 |
| 原 Commit | n/a | checkpoint.git_commit |
| 原 Artifact | n/a | artifact (run, logical_name, sha256) |
| 失败分类 | reject | task_attempt.failure_class |

## 断言结果

- ✅ same key with a different body is refused：`True`
- ✅ same key with the same body still replays the original response：`['replayed', {'receipt': 'r'}]`

## 遗留影响

无。冲突请求未被执行。

> 没有执行过的检查记为「未执行」，不记为「通过」。
