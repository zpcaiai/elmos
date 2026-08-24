# P02 实施 Backlog

## 使用规则

- 每项任务必须进入 P04 Task DAG，并绑定 owner、依赖、预算、系统 ETA、验收和证据。
- “完成”列由 P05 Gate 更新；人工/Agent 不直接设置。
- 发现新范围时新增任务，不把任务描述无限扩张。

| Task ID | Capability | 阶段 | 任务 | 初始状态 | Done evidence |
| --- | --- | --- | --- | --- | --- |
| P02-T001 | P02-C01 | Contract | 定义 Repository Inventory Scanner 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P02-T002 | P02-C01 | MVP | 实现 Repository Inventory Scanner 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P02-T003 | P02-C01 | Reliability | 为 Repository Inventory Scanner 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P02-T004 | P02-C01 | GA | 完成 Repository Inventory Scanner 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P02-T005 | P02-C02 | Contract | 定义 Language & Framework Detectors 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P02-T006 | P02-C02 | MVP | 实现 Language & Framework Detectors 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P02-T007 | P02-C02 | Reliability | 为 Language & Framework Detectors 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P02-T008 | P02-C02 | GA | 完成 Language & Framework Detectors 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P02-T009 | P02-C03 | Contract | 定义 AST & Symbol Index 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P02-T010 | P02-C03 | MVP | 实现 AST & Symbol Index 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P02-T011 | P02-C03 | Reliability | 为 AST & Symbol Index 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P02-T012 | P02-C03 | GA | 完成 AST & Symbol Index 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P02-T013 | P02-C04 | Contract | 定义 LSP Semantic Navigation 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P02-T014 | P02-C04 | MVP | 实现 LSP Semantic Navigation 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P02-T015 | P02-C04 | Reliability | 为 LSP Semantic Navigation 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P02-T016 | P02-C04 | GA | 完成 LSP Semantic Navigation 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P02-T017 | P02-C05 | Contract | 定义 Program Graph Builder 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P02-T018 | P02-C05 | MVP | 实现 Program Graph Builder 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P02-T019 | P02-C05 | Reliability | 为 Program Graph Builder 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P02-T020 | P02-C05 | GA | 完成 Program Graph Builder 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P02-T021 | P02-C06 | Contract | 定义 Platform Graph Builder 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P02-T022 | P02-C06 | MVP | 实现 Platform Graph Builder 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P02-T023 | P02-C06 | Reliability | 为 Platform Graph Builder 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P02-T024 | P02-C06 | GA | 完成 Platform Graph Builder 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P02-T025 | P02-C07 | Contract | 定义 Runtime Trace Ingestor 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P02-T026 | P02-C07 | MVP | 实现 Runtime Trace Ingestor 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P02-T027 | P02-C07 | Reliability | 为 Runtime Trace Ingestor 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P02-T028 | P02-C07 | GA | 完成 Runtime Trace Ingestor 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P02-T029 | P02-C08 | Contract | 定义 Canonical Semantic IR 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P02-T030 | P02-C08 | MVP | 实现 Canonical Semantic IR 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P02-T031 | P02-C08 | Reliability | 为 Canonical Semantic IR 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P02-T032 | P02-C08 | GA | 完成 Canonical Semantic IR 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P02-T033 | P02-C09 | Contract | 定义 Capability Discovery Engine 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P02-T034 | P02-C09 | MVP | 实现 Capability Discovery Engine 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P02-T035 | P02-C09 | Reliability | 为 Capability Discovery Engine 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P02-T036 | P02-C09 | GA | 完成 Capability Discovery Engine 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P02-T037 | P02-C10 | Contract | 定义 Provenance & Confidence Engine 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P02-T038 | P02-C10 | MVP | 实现 Provenance & Confidence Engine 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P02-T039 | P02-C10 | Reliability | 为 Provenance & Confidence Engine 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P02-T040 | P02-C10 | GA | 完成 Provenance & Confidence Engine 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P02-T041 | P02-C11 | Contract | 定义 Incremental Analysis Cache 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P02-T042 | P02-C11 | MVP | 实现 Incremental Analysis Cache 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P02-T043 | P02-C11 | Reliability | 为 Incremental Analysis Cache 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P02-T044 | P02-C11 | GA | 完成 Incremental Analysis Cache 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P02-T045 | P02-C12 | Contract | 定义 Repository Query Service 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P02-T046 | P02-C12 | MVP | 实现 Repository Query Service 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P02-T047 | P02-C12 | Reliability | 为 Repository Query Service 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P02-T048 | P02-C12 | GA | 完成 Repository Query Service 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |

## 优先级

1. Contract/Schema/Benchmark/Security baseline。
2. 一个真实 Vertical Slice 的端到端证据闭环。
3. 失败恢复、并发、多租户与成本治理。
4. 技术矩阵扩展、性能优化和商业 GA。
