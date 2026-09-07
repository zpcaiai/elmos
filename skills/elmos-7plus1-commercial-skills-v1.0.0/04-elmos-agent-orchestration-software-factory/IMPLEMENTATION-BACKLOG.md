# P04 实施 Backlog

## 使用规则

- 每项任务必须进入 P04 Task DAG，并绑定 owner、依赖、预算、系统 ETA、验收和证据。
- “完成”列由 P05 Gate 更新；人工/Agent 不直接设置。
- 发现新范围时新增任务，不把任务描述无限扩张。

| Task ID | Capability | 阶段 | 任务 | 初始状态 | Done evidence |
| --- | --- | --- | --- | --- | --- |
| P04-T001 | P04-C01 | Contract | 定义 Workflow & Tracker Adapters 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P04-T002 | P04-C01 | MVP | 实现 Workflow & Tracker Adapters 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P04-T003 | P04-C01 | Reliability | 为 Workflow & Tracker Adapters 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P04-T004 | P04-C01 | GA | 完成 Workflow & Tracker Adapters 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P04-T005 | P04-C02 | Contract | 定义 Reconciliation Scheduler 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P04-T006 | P04-C02 | MVP | 实现 Reconciliation Scheduler 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P04-T007 | P04-C02 | Reliability | 为 Reconciliation Scheduler 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P04-T008 | P04-C02 | GA | 完成 Reconciliation Scheduler 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P04-T009 | P04-C03 | Contract | 定义 Task DAG Orchestrator 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P04-T010 | P04-C03 | MVP | 实现 Task DAG Orchestrator 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P04-T011 | P04-C03 | Reliability | 为 Task DAG Orchestrator 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P04-T012 | P04-C03 | GA | 完成 Task DAG Orchestrator 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P04-T013 | P04-C04 | Contract | 定义 Workspace/Worktree Manager 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P04-T014 | P04-C04 | MVP | 实现 Workspace/Worktree Manager 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P04-T015 | P04-C04 | Reliability | 为 Workspace/Worktree Manager 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P04-T016 | P04-C04 | GA | 完成 Workspace/Worktree Manager 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P04-T017 | P04-C05 | Contract | 定义 Specialized Agent Registry 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P04-T018 | P04-C05 | MVP | 实现 Specialized Agent Registry 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P04-T019 | P04-C05 | Reliability | 为 Specialized Agent Registry 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P04-T020 | P04-C05 | GA | 完成 Specialized Agent Registry 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P04-T021 | P04-C06 | Contract | 定义 Continuable Collaboration Manager 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P04-T022 | P04-C06 | MVP | 实现 Continuable Collaboration Manager 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P04-T023 | P04-C06 | Reliability | 为 Continuable Collaboration Manager 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P04-T024 | P04-C06 | GA | 完成 Continuable Collaboration Manager 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P04-T025 | P04-C07 | Contract | 定义 Admission & Concurrency Controller 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P04-T026 | P04-C07 | MVP | 实现 Admission & Concurrency Controller 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P04-T027 | P04-C07 | Reliability | 为 Admission & Concurrency Controller 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P04-T028 | P04-C07 | GA | 完成 Admission & Concurrency Controller 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P04-T029 | P04-C08 | Contract | 定义 Recovery & Doom-loop Controller 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P04-T030 | P04-C08 | MVP | 实现 Recovery & Doom-loop Controller 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P04-T031 | P04-C08 | Reliability | 为 Recovery & Doom-loop Controller 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P04-T032 | P04-C08 | GA | 完成 Recovery & Doom-loop Controller 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P04-T033 | P04-C09 | Contract | 定义 Workpad & Progress Journal 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P04-T034 | P04-C09 | MVP | 实现 Workpad & Progress Journal 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P04-T035 | P04-C09 | Reliability | 为 Workpad & Progress Journal 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P04-T036 | P04-C09 | GA | 完成 Workpad & Progress Journal 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P04-T037 | P04-C10 | Contract | 定义 Review & Feedback Coordinator 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P04-T038 | P04-C10 | MVP | 实现 Review & Feedback Coordinator 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P04-T039 | P04-C10 | Reliability | 为 Review & Feedback Coordinator 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P04-T040 | P04-C10 | GA | 完成 Review & Feedback Coordinator 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P04-T041 | P04-C11 | Contract | 定义 Proof-of-Work Assembler 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P04-T042 | P04-C11 | MVP | 实现 Proof-of-Work Assembler 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P04-T043 | P04-C11 | Reliability | 为 Proof-of-Work Assembler 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P04-T044 | P04-C11 | GA | 完成 Proof-of-Work Assembler 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P04-T045 | P04-C12 | Contract | 定义 Operations Dashboard 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P04-T046 | P04-C12 | MVP | 实现 Operations Dashboard 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P04-T047 | P04-C12 | Reliability | 为 Operations Dashboard 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P04-T048 | P04-C12 | GA | 完成 Operations Dashboard 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |

## 优先级

1. Contract/Schema/Benchmark/Security baseline。
2. 一个真实 Vertical Slice 的端到端证据闭环。
3. 失败恢复、并发、多租户与成本治理。
4. 技术矩阵扩展、性能优化和商业 GA。
