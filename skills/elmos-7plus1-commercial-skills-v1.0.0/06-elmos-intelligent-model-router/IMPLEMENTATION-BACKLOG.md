# P06 实施 Backlog

## 使用规则

- 每项任务必须进入 P04 Task DAG，并绑定 owner、依赖、预算、系统 ETA、验收和证据。
- “完成”列由 P05 Gate 更新；人工/Agent 不直接设置。
- 发现新范围时新增任务，不把任务描述无限扩张。

| Task ID | Capability | 阶段 | 任务 | 初始状态 | Done evidence |
| --- | --- | --- | --- | --- | --- |
| P06-T001 | P06-C01 | Contract | 定义 Model/Provider Catalog 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P06-T002 | P06-C01 | MVP | 实现 Model/Provider Catalog 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P06-T003 | P06-C01 | Reliability | 为 Model/Provider Catalog 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P06-T004 | P06-C01 | GA | 完成 Model/Provider Catalog 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P06-T005 | P06-C02 | Contract | 定义 Task Classifier 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P06-T006 | P06-C02 | MVP | 实现 Task Classifier 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P06-T007 | P06-C02 | Reliability | 为 Task Classifier 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P06-T008 | P06-C02 | GA | 完成 Task Classifier 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P06-T009 | P06-C03 | Contract | 定义 Hard Constraint Engine 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P06-T010 | P06-C03 | MVP | 实现 Hard Constraint Engine 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P06-T011 | P06-C03 | Reliability | 为 Hard Constraint Engine 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P06-T012 | P06-C03 | GA | 完成 Hard Constraint Engine 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P06-T013 | P06-C04 | Contract | 定义 Benchmark & Availability Gate 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P06-T014 | P06-C04 | MVP | 实现 Benchmark & Availability Gate 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P06-T015 | P06-C04 | Reliability | 为 Benchmark & Availability Gate 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P06-T016 | P06-C04 | GA | 完成 Benchmark & Availability Gate 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P06-T017 | P06-C05 | Contract | 定义 Historical Task-Fit Store 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P06-T018 | P06-C05 | MVP | 实现 Historical Task-Fit Store 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P06-T019 | P06-C05 | Reliability | 为 Historical Task-Fit Store 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P06-T020 | P06-C05 | GA | 完成 Historical Task-Fit Store 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P06-T021 | P06-C06 | Contract | 定义 Multi-objective Scorer 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P06-T022 | P06-C06 | MVP | 实现 Multi-objective Scorer 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P06-T023 | P06-C06 | Reliability | 为 Multi-objective Scorer 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P06-T024 | P06-C06 | GA | 完成 Multi-objective Scorer 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P06-T025 | P06-C07 | Contract | 定义 Routing Execution Plane 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P06-T026 | P06-C07 | MVP | 实现 Routing Execution Plane 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P06-T027 | P06-C07 | Reliability | 为 Routing Execution Plane 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P06-T028 | P06-C07 | GA | 完成 Routing Execution Plane 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P06-T029 | P06-C08 | Contract | 定义 Long-context Audit Router 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P06-T030 | P06-C08 | MVP | 实现 Long-context Audit Router 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P06-T031 | P06-C08 | Reliability | 为 Long-context Audit Router 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P06-T032 | P06-C08 | GA | 完成 Long-context Audit Router 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P06-T033 | P06-C09 | Contract | 定义 Multimodal Router 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P06-T034 | P06-C09 | MVP | 实现 Multimodal Router 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P06-T035 | P06-C09 | Reliability | 为 Multimodal Router 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P06-T036 | P06-C09 | GA | 完成 Multimodal Router 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P06-T037 | P06-C10 | Contract | 定义 Cost/Token/ETA Engine 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P06-T038 | P06-C10 | MVP | 实现 Cost/Token/ETA Engine 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P06-T039 | P06-C10 | Reliability | 为 Cost/Token/ETA Engine 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P06-T040 | P06-C10 | GA | 完成 Cost/Token/ETA Engine 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P06-T041 | P06-C11 | Contract | 定义 Privacy & Data Policy Broker 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P06-T042 | P06-C11 | MVP | 实现 Privacy & Data Policy Broker 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P06-T043 | P06-C11 | Reliability | 为 Privacy & Data Policy Broker 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P06-T044 | P06-C11 | GA | 完成 Privacy & Data Policy Broker 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P06-T045 | P06-C12 | Contract | 定义 Route Observability 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P06-T046 | P06-C12 | MVP | 实现 Route Observability 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P06-T047 | P06-C12 | Reliability | 为 Route Observability 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P06-T048 | P06-C12 | GA | 完成 Route Observability 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |

## 优先级

1. Contract/Schema/Benchmark/Security baseline。
2. 一个真实 Vertical Slice 的端到端证据闭环。
3. 失败恢复、并发、多租户与成本治理。
4. 技术矩阵扩展、性能优化和商业 GA。
