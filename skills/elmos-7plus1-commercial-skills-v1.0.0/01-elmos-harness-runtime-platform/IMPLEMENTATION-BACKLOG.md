# P01 实施 Backlog

## 使用规则

- 每项任务必须进入 P04 Task DAG，并绑定 owner、依赖、预算、系统 ETA、验收和证据。
- “完成”列由 P05 Gate 更新；人工/Agent 不直接设置。
- 发现新范围时新增任务，不把任务描述无限扩张。

| Task ID | Capability | 阶段 | 任务 | 初始状态 | Done evidence |
| --- | --- | --- | --- | --- | --- |
| P01-T001 | P01-C01 | Contract | 定义 Harness SPI & Adapter SDK 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P01-T002 | P01-C01 | MVP | 实现 Harness SPI & Adapter SDK 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P01-T003 | P01-C01 | Reliability | 为 Harness SPI & Adapter SDK 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P01-T004 | P01-C01 | GA | 完成 Harness SPI & Adapter SDK 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P01-T005 | P01-C02 | Contract | 定义 Reversible Plugin Context 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P01-T006 | P01-C02 | MVP | 实现 Reversible Plugin Context 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P01-T007 | P01-C02 | Reliability | 为 Reversible Plugin Context 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P01-T008 | P01-C02 | GA | 完成 Reversible Plugin Context 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P01-T009 | P01-C03 | Contract | 定义 Event-Sourced Session Runtime 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P01-T010 | P01-C03 | MVP | 实现 Event-Sourced Session Runtime 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P01-T011 | P01-C03 | Reliability | 为 Event-Sourced Session Runtime 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P01-T012 | P01-C03 | GA | 完成 Event-Sourced Session Runtime 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P01-T013 | P01-C04 | Contract | 定义 Tool Runtime 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P01-T014 | P01-C04 | MVP | 实现 Tool Runtime 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P01-T015 | P01-C04 | Reliability | 为 Tool Runtime 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P01-T016 | P01-C04 | GA | 完成 Tool Runtime 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P01-T017 | P01-C05 | Contract | 定义 Async Task Runtime 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P01-T018 | P01-C05 | MVP | 实现 Async Task Runtime 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P01-T019 | P01-C05 | Reliability | 为 Async Task Runtime 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P01-T020 | P01-C05 | GA | 完成 Async Task Runtime 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P01-T021 | P01-C06 | Contract | 定义 Subagent Runtime 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P01-T022 | P01-C06 | MVP | 实现 Subagent Runtime 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P01-T023 | P01-C06 | Reliability | 为 Subagent Runtime 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P01-T024 | P01-C06 | GA | 完成 Subagent Runtime 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P01-T025 | P01-C07 | Contract | 定义 Permission & Approval Plane 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P01-T026 | P01-C07 | MVP | 实现 Permission & Approval Plane 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P01-T027 | P01-C07 | Reliability | 为 Permission & Approval Plane 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P01-T028 | P01-C07 | GA | 完成 Permission & Approval Plane 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P01-T029 | P01-C08 | Contract | 定义 Sandbox & Workspace Runtime 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P01-T030 | P01-C08 | MVP | 实现 Sandbox & Workspace Runtime 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P01-T031 | P01-C08 | Reliability | 为 Sandbox & Workspace Runtime 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P01-T032 | P01-C08 | GA | 完成 Sandbox & Workspace Runtime 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P01-T033 | P01-C09 | Contract | 定义 Context & Compaction Runtime 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P01-T034 | P01-C09 | MVP | 实现 Context & Compaction Runtime 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P01-T035 | P01-C09 | Reliability | 为 Context & Compaction Runtime 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P01-T036 | P01-C09 | GA | 完成 Context & Compaction Runtime 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P01-T037 | P01-C10 | Contract | 定义 LSP Capability Seam 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P01-T038 | P01-C10 | MVP | 实现 LSP Capability Seam 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P01-T039 | P01-C10 | Reliability | 为 LSP Capability Seam 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P01-T040 | P01-C10 | GA | 完成 LSP Capability Seam 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P01-T041 | P01-C11 | Contract | 定义 Runtime Server & SDK 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P01-T042 | P01-C11 | MVP | 实现 Runtime Server & SDK 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P01-T043 | P01-C11 | Reliability | 为 Runtime Server & SDK 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P01-T044 | P01-C11 | GA | 完成 Runtime Server & SDK 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P01-T045 | P01-C12 | Contract | 定义 Readiness & Conformance 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P01-T046 | P01-C12 | MVP | 实现 Readiness & Conformance 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P01-T047 | P01-C12 | Reliability | 为 Readiness & Conformance 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P01-T048 | P01-C12 | GA | 完成 Readiness & Conformance 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |

## 优先级

1. Contract/Schema/Benchmark/Security baseline。
2. 一个真实 Vertical Slice 的端到端证据闭环。
3. 失败恢复、并发、多租户与成本治理。
4. 技术矩阵扩展、性能优化和商业 GA。
