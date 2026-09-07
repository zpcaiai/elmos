# P05 实施 Backlog

## 使用规则

- 每项任务必须进入 P04 Task DAG，并绑定 owner、依赖、预算、系统 ETA、验收和证据。
- “完成”列由 P05 Gate 更新；人工/Agent 不直接设置。
- 发现新范围时新增任务，不把任务描述无限扩张。

| Task ID | Capability | 阶段 | 任务 | 初始状态 | Done evidence |
| --- | --- | --- | --- | --- | --- |
| P05-T001 | P05-C01 | Contract | 定义 Requirement Coverage Ledger 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P05-T002 | P05-C01 | MVP | 实现 Requirement Coverage Ledger 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P05-T003 | P05-C01 | Reliability | 为 Requirement Coverage Ledger 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P05-T004 | P05-C01 | GA | 完成 Requirement Coverage Ledger 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P05-T005 | P05-C02 | Contract | 定义 Capability Coverage Ledger 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P05-T006 | P05-C02 | MVP | 实现 Capability Coverage Ledger 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P05-T007 | P05-C02 | Reliability | 为 Capability Coverage Ledger 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P05-T008 | P05-C02 | GA | 完成 Capability Coverage Ledger 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P05-T009 | P05-C03 | Contract | 定义 Mechanical Completion Gate 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P05-T010 | P05-C03 | MVP | 实现 Mechanical Completion Gate 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P05-T011 | P05-C03 | Reliability | 为 Mechanical Completion Gate 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P05-T012 | P05-C03 | GA | 完成 Mechanical Completion Gate 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P05-T013 | P05-C04 | Contract | 定义 Verification Planner 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P05-T014 | P05-C04 | MVP | 实现 Verification Planner 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P05-T015 | P05-C04 | Reliability | 为 Verification Planner 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P05-T016 | P05-C04 | GA | 完成 Verification Planner 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P05-T017 | P05-C05 | Contract | 定义 Compiler & Static Pipeline 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P05-T018 | P05-C05 | MVP | 实现 Compiler & Static Pipeline 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P05-T019 | P05-C05 | Reliability | 为 Compiler & Static Pipeline 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P05-T020 | P05-C05 | GA | 完成 Compiler & Static Pipeline 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P05-T021 | P05-C06 | Contract | 定义 Contract & Integration Pipeline 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P05-T022 | P05-C06 | MVP | 实现 Contract & Integration Pipeline 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P05-T023 | P05-C06 | Reliability | 为 Contract & Integration Pipeline 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P05-T024 | P05-C06 | GA | 完成 Contract & Integration Pipeline 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P05-T025 | P05-C07 | Contract | 定义 Differential Runtime 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P05-T026 | P05-C07 | MVP | 实现 Differential Runtime 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P05-T027 | P05-C07 | Reliability | 为 Differential Runtime 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P05-T028 | P05-C07 | GA | 完成 Differential Runtime 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P05-T029 | P05-C08 | Contract | 定义 Generative Testing 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P05-T030 | P05-C08 | MVP | 实现 Generative Testing 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P05-T031 | P05-C08 | Reliability | 为 Generative Testing 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P05-T032 | P05-C08 | GA | 完成 Generative Testing 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P05-T033 | P05-C09 | Contract | 定义 UI & Multimodal Verifier 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P05-T034 | P05-C09 | MVP | 实现 UI & Multimodal Verifier 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P05-T035 | P05-C09 | Reliability | 为 UI & Multimodal Verifier 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P05-T036 | P05-C09 | GA | 完成 UI & Multimodal Verifier 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P05-T037 | P05-C10 | Contract | 定义 Nonfunctional Verification 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P05-T038 | P05-C10 | MVP | 实现 Nonfunctional Verification 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P05-T039 | P05-C10 | Reliability | 为 Nonfunctional Verification 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P05-T040 | P05-C10 | GA | 完成 Nonfunctional Verification 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P05-T041 | P05-C11 | Contract | 定义 Diagnosis & Repair Loop 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P05-T042 | P05-C11 | MVP | 实现 Diagnosis & Repair Loop 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P05-T043 | P05-C11 | Reliability | 为 Diagnosis & Repair Loop 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P05-T044 | P05-C11 | GA | 完成 Diagnosis & Repair Loop 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |
| P05-T045 | P05-C12 | Contract | 定义 Evidence & Certification Engine 的公共 Schema/API/事件/错误和兼容规则。 | 未开始 | P05 evidence |
| P05-T046 | P05-C12 | MVP | 实现 Evidence & Certification Engine 最小 vertical slice，并与上下游建立契约测试。 | 未开始 | P05 evidence |
| P05-T047 | P05-C12 | Reliability | 为 Evidence & Certification Engine 加入幂等、超时、取消、恢复、并发、可观测与故障注入。 | 未开始 | P05 evidence |
| P05-T048 | P05-C12 | GA | 完成 Evidence & Certification Engine 的多租户、安全、性能、运行手册、升级/回滚和商业验收。 | 未开始 | P05 evidence |

## 优先级

1. Contract/Schema/Benchmark/Security baseline。
2. 一个真实 Vertical Slice 的端到端证据闭环。
3. 失败恢复、并发、多租户与成本治理。
4. 技术矩阵扩展、性能优化和商业 GA。
