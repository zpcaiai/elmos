# 状态机

## Run

```text
pending ──► running ──► succeeded
   │           │  ▲          
   │           │  └── recovering ◄── (worker/进程/主机故障)
   │           ├──► paused ──► running
   │           ├──► failed
   └───────────┴──► cancelled
```

终态是 `succeeded` / `failed` / `cancelled`。表上的约束
`run_finished_requires_terminal_state` 保证 `finished_at` 只能在终态出现。

## Task

```text
pending ──► ready ──► running ──► succeeded
              ▲          │
              │          ├──► failed（permanent / business_conflict）
              └──────────┤
                         └──► ready（transient / lost_worker，按重试策略退避后）
blocked ──► ready        skipped / cancelled 为终态
```

`blocked` 与 `failed` 的区别很重要：`blocked` 是依赖未满足或容量不足，会自己解开；
`failed` 是这次尝试不会再自己好起来。把二者混为一谈，会让编排器要么无限重试，要么过早放弃。

## 恢复时的判定顺序

故障恢复后**不允许直接重试**。顺序必须是：

1. 核对原请求：幂等键是否已有 `completed` 记录？有就直接返回原响应。
2. 核对原 Commit：`checkpoint.git_commit` 是否已经存在？存在就说明工作已落地。
3. 核对原 Artifact：`(run, logical_name, sha256)` 是否已存在？存在就说明产物已发布。
4. 三项都没有，再决定重试，并按失败分类选退避策略。

跳过这四步直接重试，就是"任务重复执行、副作用重复产生"的标准成因。

## 事件与状态的关系

每次状态迁移和它对应的事件写在**同一个事务**里，序号在 run 行锁下分配。
因此不存在"事件描述了一个被回滚的状态"，也不存在序号空洞。
客户端拿 `Last-Event-ID` 重连，服务端回放 `seq > N` 的全部行即可。
