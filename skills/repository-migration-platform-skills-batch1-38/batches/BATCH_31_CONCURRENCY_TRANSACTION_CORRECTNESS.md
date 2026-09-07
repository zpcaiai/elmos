# Batch 31：Concurrency、Idempotency与Transaction Correctness

## Goal

在生产并发负载和故障下验证Race、Lost Update、Isolation、Linearizability、Idempotency、Outbox/Inbox和Saga。

## Inputs

- Concurrent workload models；
- Transaction semantics；
- Schedules/faults；
- Data invariants；

## Outputs

- Concurrency schedules；
- Transaction proofs/tests；
- Idempotency evidence；
- Concurrency certification；

## Execution Flow

1. 建立Actor和共享状态模型；
2. 探索Schedule；
3. 验证Isolation anomalies；
4. 验证Lease/Fencing/Single Writer；
5. 在Retry/Timeout/Cancel下验证幂等；
6. 运行Outbox/Inbox/Saga对账；

## Verification

- Race/Lost update/Partial commit为零；
- At-most-once business effect；
- Unknown commit不盲目重试；
- 死锁有检测/恢复；

## Stop Conditions

- 事务边界无法恢复；
- 跨服务强原子性无方案；
- 并发测试不稳定且无法控制；

## Gate

`Concurrency & Transaction Gate`

## Installable Skill

`agent-skills/runtime/b31-concurrency-transaction-correctness/SKILL.md`
