# Batch 09：Concurrency、Async、Memory、Lifetime与Native Semantics

## Goal

保持线程、任务、Actor、Channel、Cancellation、Ownership、ABI、Buffer与Callback等运行时语义。

## Inputs

- Concurrency graphs；
- Runtime profiles；
- Native interfaces；
- Resource lifecycles；

## Outputs

- Concurrency IR；
- Ownership/lifetime plans；
- FFI wrappers；
- Schedule tests；
- CM evidence；

## Execution Flow

1. 恢复Happens-Before与Owner；
2. 映射Task/Thread/Goroutine/Actor；
3. 生成取消、Backpressure和Shutdown；
4. 迁移GC/ARC/RAII/Ownership；
5. 验证ABI、Buffer和Callback；

## Verification

- Race/Deadlock关键Finding为零；
- 旧Generation不可提交；
- 资源所有终止路径释放；
- Native边界可重放；

## Stop Conditions

- 内存所有权不可确定；
- ABI无文档且无法测试；
- 并发模型转换扩大允许行为；

## Gate

`CM1–CM5`

## Installable Skill

`agent-skills/runtime/b09-concurrency-memory-native-semantics/SKILL.md`
